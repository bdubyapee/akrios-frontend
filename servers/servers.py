# -*- coding: utf-8 -*-
# Project: akrios_frontend
# Filename: servers.py
#
# File Description: Game Engine connection websocket.
#
# By: Jubelo
"""
    Housing the Class(es) and coroutines for receiving and maintaining a websocket connection with
    the game engine.
"""

# Standard Library
import asyncio
import json
import logging
from uuid import uuid4

# Project
from keys import WS_SECRET
from messaging.messages import messages_to_game
from messaging import parse
from clients import clients

# Third Party

log: logging.getLogger = logging.getLogger(__name__)

connections: dict = {}


class GameConnection:
    """
        Each connection when created in async ws_handler will instance this class.  This needs
        fleshed out more for smoother soft boot operation. **

        Instance variables:
            self.state is the current state of the game connection
            self.uuid is a str(uuid.uuid4()) used for unique game connection session tracking
    """
    def __init__(self) -> None:
        self.state: dict[str, bool] = {"connected": True}
        self.uuid: str = str(uuid4())

    def place_holder_1(self) -> None:
        """
        This is a placeholder to make the linter happy until I get to expanding upon the
        softboot system.
        """

    def place_holder_2(self) -> None:
        """
        This is a placeholder to make the linter happy until I get to expanding upon the
        softboot system.
        """


def register_client(game_connection) -> None:
    """
        Upon a new game connection, we register it to the GameConnection Class.
    """
    log.debug("servers.py:register_client - Adding game %s to connections",
              game_connection.uuid)
    connections[game_connection.uuid] = game_connection


def unregister_client(game_connection) -> None:
    """
        Upon an existing game disconnecting, we unregister it.
    """
    if game_connection.uuid in connections:
        log.debug(
            "servers.py:unregister_client - Deleting game %s from connections",
            game_connection.uuid)
        connections.pop(game_connection.uuid)


async def ws_heartbeat(websocket_, game_connection) -> None:
    """
        Create a JSON heartbeat payload, create the send task, then await a 10 second sleep.
        This effectively sends a heartbeat to the game engine every 10 seconds.
    """
    while game_connection.state["connected"]:
        msg: dict[str, str | int] = {
            "event": "heartbeat",
            "tasks": len(asyncio.all_tasks()),
            "secret": WS_SECRET,
        }

        log.info(msg)

        asyncio.create_task(
            websocket_.send(json.dumps(msg, sort_keys=True, indent=4)))
        await asyncio.sleep(10)


async def softboot_connection_list(websocket_) -> None:
    """
        When a game connects to this front end, part of the handler's responsibility
        is to verify if there are current connections to this front end.  If so then we may
        assume that the game/FE have performed a "soft boot", or the game was restarted after a
        crash.

        Create a JSON message to the game to indicate the session ID to player name mapping
        so that the player(s) may be logged back in automatically.
    """
    sessions = {}
    for session_id, client in clients.connections.items():
        sessions[session_id] = [client.name.lower(), client.addr, client.port]

    payload: dict = {"players": sessions}
    msg: dict[str, str | int] = {
        "event": "game/load_players",
        "secret": WS_SECRET,
        "payload": payload,
    }
    log.debug(
        "servers.py:softboot_connection_list - Notifying game engine of connections:\n\r%s",
        msg)
    await websocket_.send(json.dumps(msg, sort_keys=True, indent=4))


async def ws_read(websocket_, game_connection) -> None:
    """
        We want this coroutine to run while the game is connected, so we begin with a while loop.
        We first await control back to the main loop until we have received some data from the game.
        We then create a task to parse / handle the message from the game engine.
    """
    while game_connection.state["connected"]:
        if data := await websocket_.recv():
            log.debug("servers.py:ws_read - Received from game: %s", str(data))
            asyncio.create_task(parse.message_parse(data))
        else:
            game_connection.state["connected"] = False  # EOF Disconnect


async def ws_write(websocket_, game_connection) -> None:
    """
        We want this coroutine to run while the game is connected, so we begin with a while loop.
        Await for the messages_to_game Queue to have a message for the game.
        Create a task to send that message to the game engine.
    """
    while game_connection.state["connected"]:
        msg_obj = await messages_to_game.get()
        log.debug("servers.py:ws_write - Message sent to game: %s",
                  msg_obj.msg)

        asyncio.create_task(websocket_.send(msg_obj.msg))


async def ws_handler(websocket_, path) -> None:
    """
        This is a generic websocket handler/"shell".  It is called on new connections of websocket
        clients, which would be the game connecting to this front end.

        Start by taking our new connection, instantiate a GameConnection and register it.
        Create our three coroutine tasks associated with _this connection_.

        This coroutine will run while we have active coroutines associated with it.

    """
    game_connection: GameConnection = GameConnection()
    register_client(game_connection)

    log.debug(
        "servers.py:ws_handler - Received websocket connection from game at : %s %s",
        websocket_, path)

    tasks: list[asyncio.tasks] = [
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

    asyncio.current_task().set_name(
        f"WS: {game_connection.uuid} handler")  # type: ignore

    # When a game connection to this front end happens, we make an assumption that if we have
    # clients in clients.PlayerConnection.connections that the game has "softboot"ed or has
    # crashed and restarted.  Await a coroutine which informs the game of those client
    # details so that they can be automatically logged back in within the engine.
    if clients.connections:
        log.debug(
            "servers.py:ws_handler - Game connected to Front End.  Clients exist, await "
            "softboot_connection_list")
        await softboot_connection_list(websocket_)

    await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

    # Cancel any tasks associated with the 'current' game connection based on task name
    # containing a uuid for that connection.  This prevents the softboot, client and any other
    # task from cancelling unless they were specific to the connection.
    for task in asyncio.all_tasks():
        if game_connection.uuid in task.get_name():
            task.cancel()

    unregister_client(game_connection)
    log.info("servers.py:ws_handler - Closing websocket")
