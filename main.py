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

    def __init__(self, addr, port, state=None):
        self.addr = addr
        self.port = port
        self.state = state
        self.uuid = str(uuid4())

        self.outbound_data = []

    @classmethod
    def add_client(cls, client):
        log.info(f'Adding client {client.uuid} to connections')
        cls.connections[client.uuid] = client

    @classmethod
    def del_client(cls, client):
        if client.uuid in cls.connections:
            log.info(f'Deleting client {client.uuid} from connections')
            cls.connections.pop(client.uuid)
        else:
            log.warning(f'Failed to delete {client.uuid} from connections')


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
        addr, port = process.get_extra_info('peername')
    else:
        conn_type = 'telnet'
        process = None
        reader = args[0]
        writer = args[1]
        addr, port = writer.get_extra_info('peername')

    connection = PlayerConnection(addr, port, 'connected')
    connection.add_client(connection)

    writer.write(f'\r\nConnecting you to Akrios...\n\r ')

    while True:
        inp = await reader.readline()
        if inp:
            log.debug(f"Received Input of: {inp}")
            payload = {'uuid': connection.uuid,
                       'addr': addr,
                       'port': port,
                       'msg': inp.strip()}
            msg = {'event': 'player/input',
                   'secret': FRONT_END,
                   'payload': payload}
            GameConnection.data_to_akrios.append(json.dumps(msg, sort_keys=True, indent=4))
            log.debug(f"handle_client after input: {GameConnection.data_to_akrios}")
        if connection.outbound_data:
            writer.write(connection.outbound_data.pop(0))
        await writer.drain()
        if 'quit-console' in inp:
            break

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

    data_to_akrios = []

    def __init__(self, state=None):
        self.state = state
        self.uuid = str(uuid4())

    @classmethod
    def add_client(cls, client):
        log.info(f'Adding client {client.uuid} to connections')
        cls.connections[client.uuid] = client

    @classmethod
    def del_client(cls, client):
        if client.uuid in cls.connections:
            log.info(f'Deleting client {client.uuid} from connections')
            cls.connections.pop(client.uuid)
        else:
            log.warning(f'Failed to delete {client.uuid} from connections')

    @classmethod
    async def data_to_send(cls):
        if cls.data_to_akrios:
            log.info(f'data_to_send: {cls.data_to_akrios}')
            return cls.data_to_akrios.pop(0)


async def ws_handler(websocket_, path):
    connection = GameConnection('connected')
    connection.add_client(connection)

    log.info(f'Received websocket connection from Akrios.')

    while True:
        try:
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
                        player = PlayerConnection.connections[msg['payload']['uuid']]
                        player.outbound_data.append(msg['payload']['msg'])

                if msg['event'] == 'heartbeat':
                    log.info('Received Heartbeat!')

            message = await GameConnection.data_to_send()
            log.info(f'in ws_handler message is: {message}')
            if message:
                await websocket_.send(message)

        except Exception as err_:
            log.warning(f'Error in ws_handler: {err_}')
            break

    connection.del_client(connection)

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
