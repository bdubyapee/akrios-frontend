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
from uuid import uuid4

# Standard Library Typing
from typing import (
    Any,
    ClassVar,
    Dict,
    List
)

# Third Party

# Project
from messages import Message
from messages import messages_to_game
import clients
from keys import WS_SECRET
import parse

log: logging.Logger = logging.getLogger(__name__)


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

    connections: ClassVar[Dict[str, Any]] = {}

    def __init__(self) -> None:
        self.state: Dict[str, bool] = {"connected": True}
        self.uuid: str = str(uuid4())

    @classmethod
    def register_client(cls, game_connection) -> None:
        """
            Upon a new game connection, we register it to the GameConnection Class.
        """
        cls.connections[game_connection.uuid] = game_connection

    @classmethod
    def unregister_client(cls, game_connection) -> None:
        """
            Upon an existing game disconnecting, we unregister it.
        """
        if game_connection.uuid in cls.connections:
            log.debug(f"Deleting game {game_connection.uuid} from connections")
            cls.connections.pop(game_connection.uuid)


async def ws_heartbeat(websocket_, game_connection: GameConnection) -> None:
    """
        Create a JSON heartbeat payload, create the send task, then await a 10 second sleep.
        This effectively sends a heartbeat to the game engine every 10 seconds.
    """
    while game_connection.state["connected"]:
        msg: Dict[str, Any] = {
            "event": "heartbeat",
            "tasks": len(asyncio.all_tasks()),
            "secret": WS_SECRET,
        }

        log.info(msg)

        asyncio.create_task(websocket_.send(json.dumps(msg, sort_keys=True, indent=4)))
        await asyncio.sleep(10)


async def softboot_connection_list(websocket_) -> None:
    """
        When a game connects to this front end, part of the handler's responsibility
        is to verify if there are current connections to this front end.  If so then we may
        assume that the game/FE have performed a "soft boot", or the game was restarted.

        Create a JSON message to the game to indicate the session ID to player name mapping
        so that the player(s) may be logged back in automatically.
    """
    sessions: Dict[str, List[str]] = {}
    for session_id, client in clients.PlayerConnection.connections.items():
        sessions[session_id] = [client.name, client.addr, client.port]

    payload: Dict[str, Dict] = {"players": sessions}
    msg: Dict[str, Any] = {
        "event": "game/load_players",
        "secret": WS_SECRET,
        "payload": payload
    }

    await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))


async def ws_read(websocket_, game_connection: GameConnection) -> None:
    """
        We want this coroutine to run while the game is connected, so we begin with a while loop.
        We first await control back to the main loop until we have received some data from the game.
        Create task to parse / handle the message from the game engine.
    """
    while game_connection.state["connected"]:
        data: str = await websocket_.recv()

        if data:
            asyncio.create_task(parse.message_parse(data))
        else:
            game_connection.state["connected"] = False  # EOF Disconnect


async def ws_write(websocket_, game_connection: GameConnection) -> None:
    """
        We want this coroutine to run while the game is connected, so we begin with a while loop.
        Await for the messages_to_game Queue to have a message for the game.
        Create a task to send that message to the game engine.
    """
    while game_connection.state["connected"]:
        msg_obj: Message = await messages_to_game.get()

        asyncio.create_task(websocket_.send(msg_obj.msg))


async def ws_handler(websocket_, path: str) -> None:
    """
        This is a generic websocket handler/"shell".  It is called on new connections of websocket
        clients, which would be the game connecting to this front end.

        Start by taking our new connection, instantiate a GameConnection and register it.
        Create our three coroutine tasks associated with _this connection_.

        This coroutine will run while we have active coroutines associated with it.

    """
    game_connection: GameConnection = GameConnection()
    game_connection.register_client(game_connection)

    log.info(f"Received websocket connection from game.")

    tasks: List[asyncio.Task] = [
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

    asyncio.current_task().set_name(f"WS: {game_connection.uuid} handler")  # type: ignore

    # When a game connection to this front end happens, we make an assumption that if have
    # clients in clients.PlayerConnection.connections that the game has "softboot"ed or has
    # crashed and restarted.  Await a coroutine which informs the game of those client
    # details so that they can be automatically logged back in.
    if clients.PlayerConnection.connections:
        await softboot_connection_list(websocket_)

    _, pending = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

    # Cancel any tasks associated with the 'current' game connection based on task name
    # containing a uuid for that connection.  This prevents the softboot, client and any other
    # task from cancelling unless they were specific to the connection.
    for each_task in asyncio.all_tasks():
        if game_connection.uuid in each_task.get_name():
            each_task.cancel()

    game_connection.unregister_client(game_connection)
    log.info(f"Closing websocket")
