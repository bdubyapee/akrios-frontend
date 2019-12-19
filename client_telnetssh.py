#! usr/bin/env python
# Project: akrios-fe
# Filename: client_telnetssh.py
#
# File Description: Client connections via Telnet and SSh.
#
# By: Jubelo
"""
    Housing the Class(es) and coroutines for accepting and maintaining connections from clients via Telnet
    and SSH.

    ! Create an akrios_ca to use for the SSH portion of the front end.  You can use the command below to
    ! generate the file. Use a passphrase during ca generation, place it in keys.py.
    !
    ! ssh-keygen -f akrios_ca

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

# Project
from keys import WS_SECRET

log = logging.getLogger(__name__)

global to_game_queue


class PlayerConnection(object):
    """
        A player connection tracking class.  Each connection when created in async handle_client will
        instantiate this class to a local scope variable.

        Class variables:
            connections(dict): uuid -> PlayerConnection instance
               key: Unique Client UUID
               value: an instance of PlayerConnection
            game_to_client(dict): uuid -> list
                key: Unique Client UUID
                value: list of strings that are message outbound to that client from the game.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.state is the current state of the client connection
            self.uuid is a str(uuid.uuid4()) for unique session tracking
    """
    connections = {}
    game_to_client = {}

    def __init__(self, addr, port, state=None):
        self.addr = addr
        self.port = port
        self.state = state
        self.uuid = str(uuid4())

    def notify_connected(self):
        """
            Create JSON message to notify the game engine of a new client connection.
            Append this message to client_to_game pipeline in server_ws.GameConnection.
        """
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/connected',
               'secret': WS_SECRET,
               'payload': payload}

        to_game_queue.append(json.dumps(msg, sort_keys=True, indent=4))

    def notify_disconnected(self):
        """
            Create JSON Payload to notify the game engine of a client disconnect.
            Append to client_to_game pipeline in server_ws.GameConnection.
        """
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/disconnected',
               'secret': WS_SECRET,
               'payload': payload}

        to_game_queue.append(json.dumps(msg, sort_keys=True, indent=4))

    @classmethod
    def register_client(cls, connection):
        """
            Upon a new client connection, we register it to the PlayerConnection Class.
        """
        log.debug(f'Adding client {connection.uuid} to connections')

        cls.connections[connection.uuid] = connection
        cls.game_to_client[connection.uuid] = []

        connection.notify_connected()

    @classmethod
    def unregister_client(cls, connection):
        """
            Upon client disconnect/quit, we unregister it from the PlayerConnection Class.
        """
        if connection.uuid in cls.connections:
            log.debug(f'Deleting connection {connection.uuid} from connections')
            cls.connections.pop(connection.uuid)
            connection.notify_disconnected()

            if connection.uuid in cls.game_to_client:
                log.debug(f'unregister_connection : Deleting game messages found outbound to connection')
                cls.game_to_client.pop(connection.uuid)
        else:
            log.warning(f'unregister_connection : {connection.uuid} not in connections!')


async def client_read(reader, connection):
    """
        Utilized by the client handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We first await control back to the main loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and appended to the
            client_to_akrios buffer.
    """
    while connection.state == 'connected':
        inp = await reader.readline()
        if not inp:  # This is an EOF.  Hard disconnect.
            connection.state = 'disconnected'
            break
        else:
            log.debug(f'Received Input of: {inp}')

            payload = {'uuid': connection.uuid,
                       'addr': connection.addr,
                       'port': connection.port,
                       'msg': inp.strip()}
            msg = {'event': 'player/input',
                   'secret': WS_SECRET,
                   'payload': payload}

            to_game_queue.append(json.dumps(msg, sort_keys=True, indent=4))


async def client_write(writer, connection):
    """
        Utilized by the client handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        If the clients uuid is a key in the akrios_to_client dict, and if the value is not an empty list....
        then we have something to send to the client!

        We pop that message from the list and write it (to a client out buffer somewhere up the chain), we
        then await control back to the main loop while waiting for the client buffer to "drain" (send data).

        If we have nothing to send to the client, we simply sleep(0) so that we have yielded control
        back up to the main event loop.
    """
    while connection.state == 'connected':
        if connection.uuid in PlayerConnection.game_to_client and PlayerConnection.game_to_client[connection.uuid]:
            writer.write(PlayerConnection.game_to_client[connection.uuid].pop(0))
            await writer.drain()
        else:
            await asyncio.sleep(0)


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
        reader = process.stdin
        writer = process.stdout
        addr, port = process.get_extra_info('peername')
    else:
        conn_type = 'telnet'
        process = None
        reader = args[0]
        writer = args[1]
        addr, port = writer.get_extra_info('peername')

    connection = PlayerConnection(addr, port, 'connected')
    connection.register_client(connection)

    writer.write(f'\r\nConnecting you to Akrios...\n\r ')

    asyncio.create_task(client_read(reader, connection))
    asyncio.create_task(client_write(writer, connection))

    try:
        while connection.state == 'connected':
            await asyncio.sleep(0)
    finally:
        connection.unregister_client(connection)

        if conn_type == 'ssh':
            process.exit(0)


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
