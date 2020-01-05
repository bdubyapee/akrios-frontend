#! usr/bin/env python
# Project: akrios-fe
# Filename: servers.py
#
# File Description: Game Engine connection websocket.
#
# By: Jubelo
"""
    Housing the Class(es) and coroutines for building and maintaining a websocket connection with
    the game engine.

    Please note the use of asyncio.sleep(0) in various loops to simply return control to the event loop.
    https://github.com/python/asyncio/issues/284
"""

# Standard Library
import asyncio
import logging
import json
import os
import time
from uuid import uuid4

# Third Party

# Project
import clients
from keys import WS_SECRET

log = logging.getLogger(__name__)


class GameConnection(object):
    """
        A game connection tracking class.  Each connection when created in async ws_handler will
        instantiate this class to a local scope variable.

        Class variables:
            connections(dict): uuid -> GameConnection instance
               key: Unique game UUID
               value: an instance of GameConnection
            client_to_game(list)
                A list of JSON strings that are messages destined to the game engine from clients.

        Instance variables:
            self.state is the current state of the client connection
            self.uuid is a str(uuid.uuid4()) used for unique game connection session tracking
    """
    connections = {}
    client_to_game = []

    def __init__(self):
        self.state = {'connected': True}
        self.uuid = str(uuid4())
        if GameConnection.connections:
            GameConnection.connections = {}

    @classmethod
    def register_client(cls, game_connection):
        """
            Upon a new game connection, we register it to the GameConnection Class.
        """
        log.debug(f'Adding game {game_connection.uuid} to connections')
        cls.connections[game_connection.uuid] = game_connection

    @classmethod
    def unregister_client(cls, game_connection):
        """
            Upon an existing game disconnecting, we unregister it.
        """
        if game_connection.uuid in cls.connections:
            log.debug(f'Deleting game {game_connection.uuid} from connections')
            cls.connections.pop(game_connection.uuid)
        else:
            log.warning(f'Failed to delete {game_connection.uuid} from game connections')


async def ws_heartbeat(websocket_, game_connection):
    """
        Utilized in the WebSocket (ws) handler.

        Create a JSON heartbeat payload, await that to send, then await a 10 second sleep.
        This effectively sends a heartbeat to the game engine every 10 seconds.
    """
    while game_connection.state['connected']:
        msg = {'event': 'heartbeat',
               'tasks': len(asyncio.all_tasks()),
               'secret': WS_SECRET}

        await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))
        await asyncio.sleep(10)


async def softboot_game(wait_time):
    """
        Utilized in the WebSocket (ws) reader.

        The game has notified that it will shutdown.  We take the wait_time, sleep that time and then
        launch the game.
    """
    await asyncio.sleep(wait_time)
    os.system("python3.8 /home/bwp/PycharmProjects/akriosmud/src/akrios.py &")


async def softboot_connection_list(websocket_):
    if clients.PlayerConnection.connections:
        sessions = dict()
        for k, v in clients.PlayerConnection.connections:
            sessions[k] = [v.name, v.addr, v.port]
        payload = {'players': sessions}
        msg = {'event': 'game/load_players',
               'secret': WS_SECRET,
               'payload': payload}

        await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))


async def ws_read(websocket_, game_connection):
    """
        Utilized in the WebSocket handler: ws_handler

        We track time between heartbeat acknowledgements from the game.

        We want this coroutine to run while the game is connected, so we begin with a while loop
        We first await control back to the main loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input.
    """
    last_heartbeat_received = time.time()

    while game_connection.state['connected']:
        inp = await websocket_.recv()
        if not inp:  # This is an EOF.   Hard disconnect.
            game_connection.state['connected'] = False
            return

        log.debug(f'Websocket Received: {inp}')
        msg = json.loads(inp)

        if 'secret' not in msg.keys() or msg['secret'] != WS_SECRET:
            log.warning('Breaking out of ws_handler as no secret in message header, or wrong key.')
            break

        if msg['event'] == 'player/output':
            session = msg['payload']['uuid']
            message = msg['payload']['message']
            if session in clients.PlayerConnection.connections:
                log.debug(f'Message Received confirmation:\n{msg}')
                clients.PlayerConnection.game_to_client[session].append(message)

        if msg['event'] == 'heartbeat':
            delta = time.time() - last_heartbeat_received
            last_heartbeat_received = time.time()
            log.debug(f'Received heartbeat response from game. Last Response {delta:.6} seconds ago.')

        if msg['event'] == 'players/sign-in':
            player = msg['payload']['name']
            session = msg['payload']['uuid']
            if session in clients.PlayerConnection.connections:
                log.debug(f'players/sign-in received for {player}@{session}')
                clients.PlayerConnection.connections[session].name = player

        if msg['event'] == 'players/sign-out':
            player = msg['payload']['name']
            session = msg['payload']['uuid']
            if session in clients.PlayerConnection.connections:
                log.debug(f'players/sign-out received for {player}@{session}')
                clients.PlayerConnection.connections[session].state['connected'] = False

        if msg['event'] == 'game/softboot':
            await softboot_game(msg['payload']['wait_time'])


async def ws_write(websocket_, game_connection):
    """
        Utilized in the WebSocket handler: ws_handler

        We want this coroutine to run while the game is connected, so we begin with a while loop
        If the client_to_game buffer has messages, pop them off the list and send them!
        If no messages, we sleep(0) as every coroutine needs to await control back to the main event loop in some way.
    """
    while game_connection.state['connected']:
        if GameConnection.client_to_game:
            message = GameConnection.client_to_game.pop(0)
            log.debug(f'ws_write sending to game : {message}')
            await websocket_.send(message)
        else:
            await asyncio.sleep(0)


async def ws_handler(websocket_, path):
    """
        This is a generic websocket handler/"shell".  It is called on new connections of websocket
        clients, which would be the game connecting to the front end.

        Start by taking our new connection, instantiate a GameConnection and register it.
        Create our three coroutine tasks associated with _this connection_.

        We want this handler coroutine to run while the game is connected , or until a quit/disconnect.
        Wrap a while connected in a try/finally.  As a coroutine we must await control back to the main
        loop at some point so we sleep(0) for that, a quit or disconnect will break out so we can clean up.
    """
    game_connection = GameConnection()
    game_connection.register_client(game_connection)

    log.info(f'Received websocket connection from game.')

    asyncio.create_task(ws_heartbeat(websocket_, game_connection), name=f'WS: {game_connection.uuid} hb')
    asyncio.create_task(ws_read(websocket_, game_connection), name=f'WS: {game_connection.uuid} read')
    asyncio.create_task(ws_write(websocket_, game_connection), name=f'WS: {game_connection.uuid} write')
    task_ws_handler = asyncio.current_task()
    task_ws_handler.set_name(f'WS: {game_connection.uuid} handler')

    if clients.PlayerConnection.connections:
        await softboot_connection_list(websocket_)

    try:
        while game_connection.state['connected']:
            await asyncio.sleep(0)
    finally:
        game_connection.unregister_client(game_connection)
        log.info(f'Closing websocket')

        await websocket_.close()
