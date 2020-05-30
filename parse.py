#! usr/bin/env python
# Project: akrios-fe
# Filename: parse.py
#
# File Description: Parse messages we receive from the game engine.
#
# By: Jubelo
"""
    Housing the coroutines for parsing JSON messages we receive from the game engine.
"""

# Standard Library
import asyncio
import logging
import json
import subprocess
import time

# Third Party
from telnetlib3 import WILL, WONT, ECHO

# Project
from messages import Message, messages_to_clients
import clients
from keys import WS_SECRET

log: logging.Logger = logging.getLogger(__name__)


async def softboot_game(wait_time):
    """
        The game has notified that it will shutdown.  We take the wait_time, sleep that time and then
        launch the game.
    """
    await asyncio.sleep(wait_time)
    subprocess.Popen(["python", "/home/bwp/PycharmProjects/akrios-ii/src/server.py"])


async def msg_heartbeat():
    log.debug(f"Heartbeat received from game at: {time.time()}")


async def msg_players_output(payload):
    """
        The msg is output for a player.  We .put that message into the asyncio.queue for that specific
        player.
    """
    session = payload["uuid"]
    message = payload["message"]
    if session in clients.connections:
        asyncio.create_task(messages_to_clients[session].put(Message("IO", message)))


async def msg_players_sign_in(payload):
    """
        We have received a player sign-in from the game engine.  We assign that authenticated name
        to the session.  Use for tracking during softboots.
    """
    player = payload["name"]
    session = payload["uuid"]
    if session in clients.connections:
        log.debug(f"players/sign-in received for {player}@{session}")
        clients.connections[session].name = player


async def msg_players_sign_out(payload) -> None:
    """
        We have received a player sign-out message from the engine.  This indicates a player has quit
        the game.  We change player session state to disconnected to end their session.
    """
    player = payload["name"]
    message = payload["message"]
    session = payload["uuid"]
    if session in clients.connections:
        log.debug(f"players/sign-out received for {player}@{session}")
        clients.connections[session].state["connected"] = False
        asyncio.create_task(messages_to_clients[session].put(Message("IO", message)))


async def msg_player_session_command(payload) -> None:
    """
        Any non standard I/O for a player session.

        Currently we use this non-I/O command to indicate to the player telnet client that it should
        or shouldn't echo locally at specific times (password entry).  Will expand in the future for
        SSH commands and Web Client.
    """
    session = payload["uuid"]
    command = payload["command"]
    if session in clients.connections:
        if clients.connections[session].conn_type == "telnet":
            if command == "do echo":
                message = (WONT, ECHO)
            elif command == "dont echo":
                message = (WILL, ECHO)
            else:
                message = (WONT, ECHO)
            asyncio.create_task(messages_to_clients[session].put(Message("COMMAND-TELNET", "", message)))


async def msg_game_softboot(payload):
    await softboot_game(int(payload["wait_time"]))


messages = {
    "players/output": msg_players_output,
    "players/sign-in": msg_players_sign_in,
    "players/sign-out": msg_players_sign_out,
    "players/login-failed": msg_players_sign_out,
    "player/session command": msg_player_session_command,
    "game/softboot": msg_game_softboot,
    "heartbeat": msg_heartbeat,
}


async def message_parse(inp):
    msg = json.loads(inp)

    if "secret" not in msg.keys() or msg["secret"] != WS_SECRET:
        log.warning("No secret in message header, or wrong key.")
        return

    if msg["event"] in messages:
        if payload := msg.get("payload"):
            asyncio.create_task(messages[str(msg["event"])](payload))
        else:
            asyncio.create_task(messages[str(msg["event"])]())
