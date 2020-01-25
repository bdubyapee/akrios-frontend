#! usr/bin/env python
# Project: akrios-fe
# Filename: clients.py
#
# File Description: Client connections via Telnet and SSh.
#
# By: Jubelo
"""
    Housing the Class(es) and coroutines for accepting and maintaining connections from clients via Telnet
    and SSH.

    Please note the use of asyncio.sleep(0) in various loops to simply return control to the event loop.
    https://github.com/python/asyncio/issues/284
"""

# Standard Library
import asyncio
import json
import logging
from uuid import uuid4

# Third Party
import asyncssh
from telnetlib3 import WILL, WONT, ECHO

# Project
from message_queues import messages_to_clients
from message_queues import messages_to_game
from keys import WS_SECRET

log = logging.getLogger(__name__)


class PlayerConnection(object):
    """
        A player connection tracking class.  Each connection when created in async handle_client will
        instantiate this class to a local scope variable.

        Class variables:
            connections(dict): uuid -> PlayerConnection instance
               key: Unique Client UUID
               value: an instance of PlayerConnection

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.state is the current state of the client connection
            self.uuid is a str(uuid.uuid4()) for unique session tracking
    """
    connections = {}

    def __init__(self, addr, port, conn_type):
        self.addr = addr
        self.port = port
        self.conn_type = conn_type
        self.state = {'connected': True,
                      'logged in': False}
        self.name = ''
        self.uuid = str(uuid4())

    async def notify_connected(self):
        """
            Create JSON message to notify the game engine of a new client connection.
            Put this message into the messages_to_game asyncio.Queue().
        """
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/connected',
               'secret': WS_SECRET,
               'payload': payload}

        await messages_to_game.put(json.dumps(msg, sort_keys=True, indent=4))

    async def notify_disconnected(self):
        """
            Create JSON Payload to notify the game engine of a client disconnect.
            Put this message into the messages_to_game asyncio.Queue().
        """
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/disconnected',
               'secret': WS_SECRET,
               'payload': payload}

        await messages_to_game.put(json.dumps(msg, sort_keys=True, indent=4))

    @classmethod
    async def register_client(cls, connection):
        """
            Upon a new client connection, we register it to the PlayerConnection Class.
        """
        log.debug(f'Adding client {connection.uuid} to connections')

        cls.connections[connection.uuid] = connection
        messages_to_clients[connection.uuid] = asyncio.Queue()

        await connection.notify_connected()

    @classmethod
    async def unregister_client(cls, connection):
        """
            Upon client disconnect/quit, we unregister it from the PlayerConnection Class.
        """
        if connection.uuid in cls.connections:
            log.debug(f'Deleting connection {connection.uuid} from connections')
            cls.connections.pop(connection.uuid)
            messages_to_clients.pop(connection.uuid)
            await connection.notify_disconnected()

        else:
            log.warning(f'unregister_connection : {connection.uuid} not in connections!')


async def client_read(reader, connection):
    """
        Utilized by the client handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We first await control back to the main loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and put into the
            messages_to_game asyncio.Queue()
    """
    while connection.state['connected']:
        inp = await reader.readline()
        if not inp:  # This is an EOF.  Hard disconnect.
            connection.state['connected'] = False
            return

        log.debug(f'Received Input of: {inp}')

        payload = {'uuid': connection.uuid,
                   'addr': connection.addr,
                   'port': connection.port,
                   'msg': inp.strip()}
        msg = {'event': 'player/input',
               'secret': WS_SECRET,
               'payload': payload}

        await messages_to_game.put(json.dumps(msg, sort_keys=True, indent=4))


async def client_write(writer, connection):
    """
        Utilized by the client handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We await for any messages from the game, then write and drain it.
    """
    while connection.state['connected']:
        message = await messages_to_clients[connection.uuid].get()
        if type(message) is str:
            writer.write(message)
        elif type(message) is tuple:
            writer.iac(message[0], message[1])
        await writer.drain()


async def handle_client(*args):
    """
    This is a generic handler/"shell".  It is called on new connections of both
    telnet and SSH clients.

    By performing the if/else blocks we can handle both Telnet and SSH
    connections via the same handler.

    This can probably be cleaner by checking the type of the positional arguments.
    Or perhaps break it into two handlers anyway.  Investigate this.
    """
    if len(args) == 1:
        conn_type = 'ssh'
        process = args[0]
        log.debug(f'SSH details are: {dir(process)}')
        reader = process.stdin
        writer = process.stdout
        addr, port = process.get_extra_info('peername')
    else:
        conn_type = 'telnet'
        process = None
        reader = args[0]
        writer = args[1]
        addr, port = writer.get_extra_info('peername')
        writer.iac(WONT, ECHO)

    connection = PlayerConnection(addr, port, conn_type)
    await connection.register_client(connection)

    tasks = [
             asyncio.create_task(client_read(reader, connection), name=f'{connection.uuid} read'),
             asyncio.create_task(client_write(writer, connection), name=f'{connection.uuid} write')
            ]
    handler_task = asyncio.current_task()
    handler_task.set_name(f'{connection.uuid} handler')

    done, rest = await asyncio.wait(tasks, return_when='FIRST_COMPLETED')

    await connection.unregister_client(connection)

    if conn_type == 'ssh':
        process.close()
        process.exit(0)
    elif conn_type == 'telnet':
        writer.write_eof()
        writer.close()

    for each_task in rest:
        each_task.cancel()


class MySSHServer(asyncssh.SSHServer):
    """
    This class facilitates allowing SSH access in without requiring credentials.  The various methods
    are configured to allow the "unauthenticated" access as well as some logging.

    XXX Clean this up and document it.  Came from the asyncssh docs somewhere.
    """
    def connection_made(self, conn):
        log.info(f'SSH connection received from {conn.get_extra_info("peername")[0]}')

    def connection_lost(self, exc):
        if exc:
            log.warning(f'SSH connection error: {str(exc)}')
        else:
            log.info('SSH connection closed.')

    def begin_auth(self, username):
        return False

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return True
