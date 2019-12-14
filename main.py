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
    Should also allow to have connections stay up while restarting game.

    The file 'ssh_host_key' must exist with an SSH private key in it for server host key.
    The file 'ssh_host_key-cert.pub' may optionally be provided for an SSH host certificate.
    The file 'ssh_user_ca' must exist with a cert-authority entry of the certificate authority
        which can sign valid client certificates.

    https://www.digitalocean.com/community/tutorials/how-to-create-an-ssh-ca-to-validate-hosts-and-clients-with-ubuntu
"""

import asyncio
import asyncssh
import json
import logging
import telnetlib3
import time
from uuid import uuid4
import websockets

from keys import passphrase as ca_phrase
from keys import FRONT_END

logging.basicConfig(format='%(asctime)s: %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

log = logging.getLogger(__name__)


class PlayerConnection(object):
    """
        A player connection tracking class.  Each connection when created in async handle_client will
        instantiate this class to a local scope variable.  We utilize Class variable _connections
        to track all of the connections.  The instance itself will track the following:

        self.addr is the IP address portion of the peer
        self.port is the port portion of the peer
        self.state is the current state of the connection
    """
    connections = {}
    akrios_to_client = {}

    def __init__(self, addr, port, state=None):
        self.addr = addr
        self.port = port
        self.state = state
        self.uuid = str(uuid4())

    def connection_connected(self):
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/connected',
               'secret': FRONT_END,
               'payload': payload}
        GameConnection.client_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))

    def connection_disconnected(self):
        payload = {'uuid': self.uuid,
                   'addr': self.addr,
                   'port': self.port}
        msg = {'event': 'connection/disconnected',
               'secret': FRONT_END,
               'payload': payload}
        GameConnection.client_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))

    @classmethod
    def add_client(cls, client):
        log.info(f'Adding client {client.uuid} to connections')
        cls.connections[client.uuid] = client
        cls.akrios_to_client[client.uuid] = []

    @classmethod
    def del_client(cls, client):
        if client.uuid in cls.connections:
            log.info(f'Deleting client {client.uuid} from connections')
            cls.connections.pop(client.uuid)
            if client.uuid in cls.akrios_to_client:
                log.info(f'del_client : Deleting akrios messages found outbound to client')
                cls.akrios_to_client.pop(client.uuid)
            for index, eachmsg in enumerate(GameConnection.client_to_akrios):
                if client.uuid in eachmsg:
                    log.info(f'del_client : Deleting client messages found inbound to Akrios')
                    GameConnection.client_to_akrios.pop(index)
        else:
            log.warning(f'Failed to delete {client.uuid} from connections')


async def client_read(reader, connection):
    while True:
        inp = await reader.readline()
        if inp:
            log.debug(f"Received Input of: {inp}")
            payload = {'uuid': connection.uuid,
                       'addr': connection.addr,
                       'port': connection.port,
                       'msg': inp.strip()}
            msg = {'event': 'player/input',
                   'secret': FRONT_END,
                   'payload': payload}
            GameConnection.client_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))
            log.debug(f"client_read after input: {GameConnection.client_to_akrios}")


async def client_write(writer, connection):
    while True:
        if connection.uuid in PlayerConnection.akrios_to_client and PlayerConnection.akrios_to_client[connection.uuid]:
            message = PlayerConnection.akrios_to_client[connection.uuid].pop(0)
            writer.write(message)
            await writer.drain()
        else:
            await asyncio.sleep(0.0000001)


async def handle_client(*args):
    """
    This is a generic handler.  By performing the if/else blocks we can handle both Telnet and SSH
    connections via the same handler.

    This can probably be cleaner by checking the type of the positional arguments.  Investigate.
    """
    if len(args) == 1:
        conn_type = 'ssh'
        process = args[0]
        reader = process.stdin
        writer = process.stdout
        # log.info(dir(process))
        addr, port = process.get_extra_info('peername')
    else:
        conn_type = 'telnet'
        process = None
        reader = args[0]
        writer = args[1]
        # log.debug(f'Reader: {dir(reader)}')
        # log.debug(f'Writer: {dir(writer)}')
        addr, port = writer.get_extra_info('peername')

    connection = PlayerConnection(addr, port, 'connected')
    connection.add_client(connection)

    writer.write(f'\r\nConnecting you to Akrios...\n\r ')

    connection.connection_connected()

    asyncio.create_task(client_read(reader, connection))
    asyncio.create_task(client_write(writer, connection))

    while True:
        try:
            await asyncio.sleep(0.0000001)
        except Exception as err_:
            log.warning(f'Exception in handle_client: {err_}')
            break

    connection.connection_disconnected()
    connection.del_client(connection)

    if conn_type == 'ssh':
        process.exit(0)
    elif conn_type == 'telnet':
        writer.close()


class MySSHServer(asyncssh.SSHServer):
    """
    This class facilitates allowing SSH access in without requiring credentials.  The various methods
    are configured to allow the "unauthenticated" access as well as some logging.
    """
    def connection_made(self, conn):
        log.info(f'SSH connection received from {conn.get_extra_info("peername")[0]}')

    def connection_lost(self, exc):
        if exc:
            log.warning(f'SSH connection error: {str(exc)}')
        else:
            log.info('SSH connection closed.')

    def begin_auth(self, username):
        # If the user's password is the empty string, no auth is required
        return False

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return True


class GameConnection(object):
    """
        A game connection tracking class.  Each connection when created in async ws_handler will
        instantiate this class to a local scope variable.  We utilize Class variable _connections
        to track all of the connections.  The instance itself will track the following:

        self.state is the current state of the game connection
    """
    connections = {}

    client_to_akrios = []

    def __init__(self, state=None):
        self.state = state
        self.uuid = str(uuid4())

    @classmethod
    def add_client(cls, client):
        log.info(f'Adding client {client.uuid} to connections')
        cls.connections[client.uuid] = client

    @classmethod
    def delete_client(cls, client):
        if client.uuid in cls.connections:
            log.info(f'Deleting client {client.uuid} from connections')
            cls.connections.pop(client.uuid)
        else:
            log.warning(f'Failed to delete {client.uuid} from connections')


async def ws_heartbeat(websocket_):
    while True:
        msg = {'event': 'heartbeat',
               'secret': FRONT_END}
        await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))
        await asyncio.sleep(10)


async def ws_read(websocket_):
    last_heartbeat_received = time.time()

    while True:
        inp = await websocket_.recv()
        if inp:
            log.info(f'WS Received: {inp}')
            msg = json.loads(inp)

            if 'secret' not in msg.keys():
                log.warning('Breaking out of ws_handler as no secret in msg')
                break
            if msg['secret'] != FRONT_END:
                log.warning('Breaking out of ws_handler as secret in msg is not correct.')
                break

            if msg['event'] == 'player/output':
                if msg['payload']['uuid'] in PlayerConnection.connections:
                    log.info(f"Message Received confirmation:\n")
                    log.info(f"{msg}")
                    PlayerConnection.akrios_to_client[msg['payload']['uuid']].append(msg['payload']['message'])

            if msg['event'] == 'heartbeat':
                delta = time.time() - last_heartbeat_received
                last_heartbeat_received = time.time()
                log.debug(f'Received heartbeat response from Akrios. Last Response {delta:.6} seconds ago.')


async def ws_write(websocket_):
    while True:
        if GameConnection.client_to_akrios:
            message = GameConnection.client_to_akrios.pop(0)
            log.info(f'Sending to Akrios : {message}')
            await websocket_.send(message)
        else:
            await asyncio.sleep(0.0000001)


async def ws_handler(websocket_, path):
    connection = GameConnection('connected')
    connection.add_client(connection)

    log.info(f'Received websocket connection from Akrios.')

    asyncio.create_task(ws_heartbeat(websocket_))
    asyncio.create_task(ws_read(websocket_))
    asyncio.create_task(ws_write(websocket_))

    while True:
        try:
            await asyncio.sleep(0.0000001)
        except Exception as err_:
            log.warning(f"Caught exception in main loop: {err_}")
            break

    connection.delete_client(connection)

    log.info(f'Closing websocket')
    await websocket_.close()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    telnet_port = 6969
    ssh_port = 7979
    ws_port = 8989

    log.info(f'Creating Telnet Listener on port {telnet_port}')
    log.info(f'Creating Websocket Listener on port {ws_port}')
    all_servers = [telnetlib3.create_server(port=telnet_port, shell=handle_client, connect_maxwait=0.5),
                   asyncssh.create_server(MySSHServer, '', ssh_port, server_host_keys=['akrios_ca'],
                                          passphrase=ca_phrase,
                                          process_factory=handle_client),
                   websockets.serve(ws_handler, 'localhost', ws_port)
                   ]

    for each_server in all_servers:
        loop.run_until_complete(each_server)

    try:
        log.info('Launching Akrios front end loop:\n\r')
        loop.run_forever()
    except Exception as err:
        log.warning(f'Error in main loop: {err}')

    for server in all_servers:
        loop.run_until_complete(server.wait_closed())
