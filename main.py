#! usr/bin/env python
# Project: akrios-fe
# Filename: main.py
# 
# File Description: Main launching point for the connection front end to Akrios.
# 
# By: Jubelo
"""
    Initial test of separating server(Socket) and game logic for Akrios.
    End game is to have several front ends available (Telnet, Secure Telnet, SSH, Web, etc)
    Should also allow to have connections stay up while restarting game

    ! Create an akrios_ca to use for the SSH portion of the front end.  You can use the command below to
    ! generate the file. Use a passphrase during ca generation, place it in keys.py.
    !
    ! ssh-keygen -f akrios_ca
"""

import asyncio
import asyncssh
import json
import logging
import signal
import telnetlib3
import time
from uuid import uuid4
import websockets

from keys import passphrase as ca_phrase
from keys import FRONT_END

logging.basicConfig(format='%(asctime)s: %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
log = logging.getLogger(__name__)
#  "The logging module changed my life."      - Jubelo


class PlayerConnection(object):
    """
        A player connection tracking class.  Each connection when created in async handle_client will
        instantiate this class to a local scope variable.

        Class variables:
            connections(dict): uuid -> PlayerConnection instance
               key: Unique Client UUID
               value: an instance of PlayerConnection
            akrios_to_client(dict): uuid -> list
                key: Unique Client UUID
                value: list of strings that are message outbound to that client from the game.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.state is the current state of the client connection
            self.uuid is a str(uuid.uuid4()) for unique session tracking
    """
    connections = {}
    akrios_to_client = {}

    def __init__(self, addr, port, state=None):
        self.addr = addr
        self.port = port
        self.state = state
        self.uuid = str(uuid4())

    def notify_connected(self):
        """
            Create JSON Payload to notify of a new client connection and append to client_to_akrios buffer.
        """
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/connected',
               'secret': FRONT_END,
               'payload': payload}

        GameConnection.client_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))

    def notify_disconnected(self):
        """
            Create JSON Payload to notify of a client disconnect and append to client_to_akrios buffer.
        """
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/disconnected',
               'secret': FRONT_END,
               'payload': payload}

        GameConnection.client_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))

    @classmethod
    def register_client(cls, client):
        """
            Upon a new client connection, we register it to the PlayerConnection Class.
        """
        log.debug(f'Adding client {client.uuid} to connections')

        cls.connections[client.uuid] = client
        cls.akrios_to_client[client.uuid] = []

        client.notify_connected()

    @classmethod
    def unregister_client(cls, client):
        """
            Upon client disconnect/quit, we unregister it.
        """
        if client.uuid in cls.connections:
            log.debug(f'Deleting client {client.uuid} from connections')
            cls.connections.pop(client.uuid)
            client.notify_disconnected()

            if client.uuid in cls.akrios_to_client:
                log.debug(f'unregister_client : Deleting akrios messages found outbound to client')
                cls.akrios_to_client.pop(client.uuid)

            for index, eachmsg in enumerate(GameConnection.client_to_akrios):
                if client.uuid in eachmsg:
                    log.debug(f'unregister_client : Deleting client messages found inbound to Akrios')
                    GameConnection.client_to_akrios.pop(index)
        else:
            log.warning(f'unregister_client : {client.uuid} not in connections!')


async def client_read(reader, connection):
    """
        read coroutine utilized by the client handler.

        We want this coroutine to run "forever", so we begin with a while True
        We first await control back to the main loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and appended to the
            client_to_akrios buffer.
    """
    while True:
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
                   'secret': FRONT_END,
                   'payload': payload}

            GameConnection.client_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))

            log.debug(f'client_read after input: {GameConnection.client_to_akrios}')


async def client_write(writer, connection):
    """
        write coroutine utilized by the client handler.

        We want this coroutine to run "forever", so we begin with a while True
        If the clients uuid is a key in the akrios_to_client dict, and if the value is not an empty list....
        then we have something to send to the client!

        We pop that message from the list and write it (to a client out buffer somewhere up the chain), we
        then await control back to the main loop while waiting for the client buffer to "drain" (send data).

        If we have nothing to send to the client, we simply sleep for a short time so that we have yielded control
        back up to the main event loop.
    """
    while True:
        if connection.uuid in PlayerConnection.akrios_to_client and PlayerConnection.akrios_to_client[connection.uuid]:
            writer.write(PlayerConnection.akrios_to_client[connection.uuid].pop(0))
            await writer.drain()
        else:
            await asyncio.sleep(0.0000001)


async def handle_client(*args):
    """
    This is a generic handler/"shell" coroutine.  It is called on new connections of both
    telnet and SSH.

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
            await asyncio.sleep(0.0000001)
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
        # If the user's password is an empty string, no auth is required
        return False

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return True


class GameConnection(object):
    """
        A game connection tracking class.  Each connection when created in async ws_handler will
        instantiate this class to a local scope variable.

        Class variables:
            connections(dict): uuid -> GameConnection instance
               key: Unique game UUID
               value: an instance of GameConnection
            client_to_akrios(dict): list
                A list of JSON strings that are message outbound to the game from clients.

        Instance variables:
            self.state is the current state of the client connection
            self.uuid is a str(uuid.uuid4()) used for unique game connection session tracking
    """
    connections = {}

    client_to_akrios = []

    def __init__(self, state=None):
        self.state = state
        self.uuid = str(uuid4())

    @classmethod
    def register_client(cls, client):
        """
            Upon a new game connection, we register it to the GameConnection Class.
        """
        log.debug(f'Adding client {client.uuid} to connections')
        cls.connections[client.uuid] = client

    @classmethod
    def unregister_client(cls, client):
        """
            Upon an existing game disconnecting, we unregister it.
        """
        if client.uuid in cls.connections:
            log.debug(f'Deleting client {client.uuid} from connections')
            cls.connections.pop(client.uuid)
        else:
            log.warning(f'Failed to delete {client.uuid} from connections')


async def ws_heartbeat(websocket_):
    """
        Heartbeat coroutine utilized in the WebSocket (ws) handler.

        Create a JSON heartbeat payload, await that to send, then await a 10 second sleep.
        This effectively sends a heartbeat to the game every 10 seconds.
    """
    while True:
        msg = {'event': 'heartbeat',
               'tasks': len(asyncio.all_tasks()),
               'secret': FRONT_END}

        await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))
        await asyncio.sleep(10)


async def ws_read(websocket_, connection):
    """
        read coroutine utilized in the WebSocket (ws) handler.

        For fun we track time between heartbeat acknowledgements from the game.

        We want this coroutine to run "forever", so we begin with a while True
        We first await control back to the main loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input (Event of some kind?  Heartbeat?  Message to client?)
    """
    last_heartbeat_received = time.time()

    while True:
        inp = await websocket_.recv()
        if not inp:  # This is an EOF.   Hard disconnect.
            connection.state = 'disconnected'
        else:
            log.debug(f'WS Received: {inp}')
            msg = json.loads(inp)

            if 'secret' not in msg.keys():
                log.warning('Breaking out of ws_handler as no secret in msg')
                break
            if msg['secret'] != FRONT_END:
                log.warning('Breaking out of ws_handler as secret in msg is not correct.')
                break

            if msg['event'] == 'player/output':
                if msg['payload']['uuid'] in PlayerConnection.connections:
                    log.debug(f'Message Received confirmation:\n')
                    log.debug(f'{msg}')
                    PlayerConnection.akrios_to_client[msg['payload']['uuid']].append(msg['payload']['message'])

            if msg['event'] == 'heartbeat':
                delta = time.time() - last_heartbeat_received
                last_heartbeat_received = time.time()
                log.debug(f'Received heartbeat response from Akrios. Last Response {delta:.6} seconds ago.')


async def ws_write(websocket_):
    """
        write coroutine utilized in the WebSocket (ws) handler.

        We want this coroutine to run "forever", so we begin with a while True
        If the client_to_akrios buffer has messages, pop them off the list and send them!
        If no messages, we "sleep" for a very short period of time as every coroutine needs to await control
            back to the main event loop in some way.
    """
    while True:
        if GameConnection.client_to_akrios:
            message = GameConnection.client_to_akrios.pop(0)
            log.debug(f'Sending to Akrios : {message}')
            await websocket_.send(message)
        else:
            await asyncio.sleep(0.0000001)


async def ws_handler(websocket_, path):
    """
        handler coroutine utilized for newly connected websocket clients.

        Start by taking our new connection, instantiate a GameConnection and register it.
        Create our three coroutine tasks associated with _this connection_.

        We want this handler coroutine to run "forever", or until a quit/disconnect.
        Wrap a while connected in a try/finally.  As a coroutine we must await control back to the main
        loop at some point so we sleep for a short time, a quit or disconnect will break out so we can clean up.
    """
    connection = GameConnection('connected')
    connection.register_client(connection)

    log.info(f'Received websocket connection from Akrios.')

    asyncio.create_task(ws_heartbeat(websocket_))
    asyncio.create_task(ws_read(websocket_, connection))
    asyncio.create_task(ws_write(websocket_))

    try:
        while connection.state == 'connected':
            await asyncio.sleep(0.0000001)
    finally:
        connection.unregister_client(connection)
        log.info(f'Closing websocket')
        await websocket_.close()


async def shutdown(signal_, loop_):
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in __main__

        Courtesy of the great "talks" by Lynn Root and her Mayhem Mandrill
        https://www.roguelynn.com/talks/
    """
    log.warning(f'Received exit signal {signal_.name}')

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    log.info(f'Cancelling {len(tasks)} outstanding tasks')
    await asyncio.gather(*tasks, return_exceptions=True)
    loop_.stop()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    # Signals catching discovered on Lynn Roots site.  Great asyncio information.
    # https://www.roguelynn.com/talks/
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s, loop)))

    telnet_port = 6969
    ssh_port = 7979
    ws_port = 8989

    log.info(f'Creating Telnet Listener on port {telnet_port}')
    log.info(f'Creating SSH Listener on port {ssh_port}')
    log.info(f'Creating Websocket Listener on port {ws_port}')
    all_servers = [telnetlib3.create_server(port=telnet_port, shell=handle_client, connect_maxwait=0.5),
                   asyncssh.create_server(MySSHServer, '', ssh_port, server_host_keys=['akrios_ca'],
                                          passphrase=ca_phrase,
                                          process_factory=handle_client),
                   websockets.serve(ws_handler, 'localhost', ws_port)
                   ]

    log.info('Launching Akrios front end loop:\n\r')

    for each_server in all_servers:
        loop.run_until_complete(each_server)

    try:
        loop.run_forever()
    except Exception as err:
        log.warning(f'Error in main loop: {err}')

    log.info('Front end shut down.')
    loop.close()
