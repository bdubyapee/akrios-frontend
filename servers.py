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
"""

# Standard Library
import asyncio
import logging
import json
import os
import time
from uuid import uuid4

# Third Party
from telnetlib3 import WILL, WONT, ECHO

# Project
from message_queues import messages_to_clients
from message_queues import messages_to_game
import clients
from keys import WS_SECRET

log = logging.getLogger(__name__)


class GameConnection(object):
    """
        A game connection tracking class.  Each connection when created in async ws_handler will
        instantiate this class to a local variable.

        Class variables:
            connections(dict): uuid -> GameConnection instance
               key: Unique game UUID
               value: an instance of GameConnection

        Instance variables:
            self.state is the current state of the game connection
            self.uuid is a str(uuid.uuid4()) used for unique game connection session tracking
    """

    connections = {}

    def __init__(self):
        self.state = {"connected": True}
        self.uuid = str(uuid4())
        if GameConnection.connections:
            GameConnection.connections = {}

    @classmethod
    def register_client(cls, game_connection):
        """
            Upon a new game connection, we register it to the GameConnection Class.
        """
        log.debug(f"Adding game {game_connection.uuid} to connections")
        cls.connections[game_connection.uuid] = game_connection

    @classmethod
    def unregister_client(cls, game_connection):
        """
            Upon an existing game disconnecting, we unregister it.
        """
        if game_connection.uuid in cls.connections:
            log.debug(f"Deleting game {game_connection.uuid} from connections")
            cls.connections.pop(game_connection.uuid)
        else:
            log.warning(
                f"Failed to delete {game_connection.uuid} from game connections"
            )


async def ws_heartbeat(websocket_, game_connection):
    """
        Utilized in the ws_handler coroutine.

        Create a JSON heartbeat payload, await that to send, then await a 10 second sleep.
        This effectively sends a heartbeat to the game engine every 10 seconds.
    """
    while game_connection.state["connected"]:
        msg = {
            "event": "heartbeat",
            "tasks": len(asyncio.all_tasks()),
            "secret": WS_SECRET,
        }

        log.info(msg)

        await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))
        await asyncio.sleep(10)


async def softboot_game(wait_time):
    """
        Utilized in the ws_read coroutine.

        The game has notified that it will shutdown.  We take the wait_time, sleep that time and then
        launch the game.
    """
    await asyncio.sleep(wait_time)
    os.system("python3.8 /home/bwp/PycharmProjects/akriosmud/src/akrios.py &")


async def softboot_connection_list(websocket_):
    """
        Utilized in the WebSocket handler: ws_handler

        When a game connects to this front end, part of the handler's responsibility
        is to verify if there are current connections to this front end.  If so then we may
        surmise that the game/FE have performed a "soft boot", or the game was restarted.

        Create a JSON message to the game to indicate the session ID to player name mapping
        so that the player(s) may be logged back in automatically.
    """
    sessions = dict()
    for k, v in clients.PlayerConnection.connections.items():
        sessions[k] = [v.name, v.addr, v.port]
    payload = {"players": sessions}
    msg = {"event": "game/load_players", "secret": WS_SECRET, "payload": payload}

    await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))


async def ws_read(websocket_, game_connection):
    """
        Utilized in the WebSocket handler: ws_handler

        We track time between heartbeat acknowledgements from the game.

        We want this coroutine to run while the game is connected, so we begin with a while loop.
        We first await control back to the main loop until we have received some data from the gam.
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the message received from the game.
    """
    last_heartbeat_received = time.time()

    while game_connection.state["connected"]:
        inp = await websocket_.recv()

        if not inp:  # This is an EOF.   Hard disconnect.
            game_connection.state["connected"] = False
            return

        log.debug(f"Websocket Received: {inp}")
        msg = json.loads(inp)

        if "secret" not in msg.keys() or msg["secret"] != WS_SECRET:
            log.warning(
                "Breaking out of ws_handler as no secret in message header, or wrong key."
            )
            break

        if msg["event"] == "players/output":
            session = msg["payload"]["uuid"]
            message = msg["payload"]["message"]
            if session in clients.PlayerConnection.connections:
                log.debug(f"Message Received confirmation:\n{msg}")
                await messages_to_clients[session].put(message)
            continue

        if msg["event"] == "heartbeat":
            delta = time.time() - last_heartbeat_received
            last_heartbeat_received = time.time()
            log.debug(
                f"Received heartbeat response from game. Last Response {delta:.6} seconds ago."
            )
            continue

        if msg["event"] == "players/sign-in":
            player = msg["payload"]["name"]
            session = msg["payload"]["uuid"]
            if session in clients.PlayerConnection.connections:
                log.debug(f"players/sign-in received for {player}@{session}")
                clients.PlayerConnection.connections[session].name = player
            continue

        if msg["event"] == "players/sign-out" or msg["event"] == "players/login-failed":
            player = msg["payload"]["name"]
            message = msg["payload"]["message"]
            session = msg["payload"]["uuid"]
            if session in clients.PlayerConnection.connections:
                log.debug(f'{msg["event"]} received for {player}@{session}')
                clients.PlayerConnection.connections[session].state["connected"] = False
                await messages_to_clients[session].put(message)
            continue

        if msg["event"] == "player/session command":
            session = msg["payload"]["uuid"]
            command = msg["payload"]["command"]
            if session in clients.PlayerConnection.connections:
                if clients.PlayerConnection.connections[session].conn_type == "telnet":
                    if command == "do echo":
                        message = (WONT, ECHO)
                    elif command == "dont echo":
                        message = (WILL, ECHO)
                    else:
                        continue
                    await messages_to_clients[session].put(message)
            continue

        if msg["event"] == "game/softboot":
            log.info("Received game/softboot event in servers receiver.")
            await softboot_game(msg["payload"]["wait_time"])


async def ws_write(websocket_, game_connection):
    """
        Utilized in the WebSocket handler: ws_handler

        We want this coroutine to run while the game is connected, so we begin with a while loop.
        Await for the messages_to_game Queue to have a message for the game.
    """
    while game_connection.state["connected"]:
        message = await messages_to_game.get()

        log.debug(f"ws_write sending to game : {message}")

        await websocket_.send(message)


async def ws_handler(websocket_, path):
    """
        This is a generic websocket handler/"shell".  It is called on new connections of websocket
        clients, which would be the game connecting to this front end.

        Start by taking our new connection, instantiate a GameConnection and register it.
        Create our three coroutine tasks associated with _this connection_.

        This coroutine will run while we have active coroutines associated with it.

    """
    game_connection = GameConnection()
    game_connection.register_client(game_connection)

    log.info(f"Received websocket connection from game.")

    tasks = [
        asyncio.create_task(
            ws_heartbeat(websocket_, game_connection),
            name=f"WS: {game_connection.uuid} hb",
        ),
        asyncio.create_task(
            ws_read(websocket_, game_connection),
            name=f"WS: {game_connection.uuid} read",
        ),
        asyncio.create_task(
            ws_write(websocket_, game_connection),
            name=f"WS: {game_connection.uuid} write",
        ),
    ]

    task_ws_handler = asyncio.current_task()
    task_ws_handler.set_name(f"WS: {game_connection.uuid} handler")

    # When a game connection to this front end happens, we make an assumption that if have
    # clients in clients.PlayerConnection.connections that the game has "softboot"ed or has
    # crashed and restarted.  Await a coroutine which informs the game of those client
    # details so that they can be automatically logged back in.
    if clients.PlayerConnection.connections:
        await softboot_connection_list(websocket_)

    # We need to be cognisant that due to the softboot_game coroutine has a slight sleep associated
    # with it prior to running the new game instance.  Using .wait instead of .gather allows us
    # to not execute beyond this line (in this coroutine) until, you guessed it, ALL tasks have completed.
    _, pending = await asyncio.wait(tasks, return_when="ALL_COMPLETED")

    game_connection.unregister_client(game_connection)
    log.info(f"Closing websocket")

    # At this point, due to .wait(ing), we should not have to cancel any tasks.
    # XXX Investigate removing this as unnecessary.
    for each_task in pending:
        each_task.cancel()
