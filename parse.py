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
from messages import Message
from messages import messages_to_clients
import clients
from keys import WS_SECRET

log = logging.getLogger(__name__)


async def softboot_game(wait_time):
    """
        The game has notified that it will shutdown.  We take the wait_time, sleep that time and then
        launch the game.
    """
    await asyncio.sleep(wait_time)
    subprocess.Popen(['python3.8', '/home/bwp/PycharmProjects/akriosmud/src/akrios.py', '&'])


async def msg_heartbeat(msg):
    log.debug(f"Heartbeat received from game at: {time.time()}")


async def msg_players_output(msg):
    """
        The msg is output for a player.  We .put that message into the asyncio.queue for that specific
        player.
    """
    session = msg["payload"]["uuid"]
    message = msg["payload"]["message"]
    if session in clients.PlayerConnection.connections:
        asyncio.create_task(messages_to_clients[session].put(Message(message, "IO")))


async def msg_players_sign_in(msg):
    player = msg["payload"]["name"]
    session = msg["payload"]["uuid"]
    if session in clients.PlayerConnection.connections:
        log.debug(f"players/sign-in received for {player}@{session}")
        clients.PlayerConnection.connections[session].name = player


async def msg_players_sign_out(msg):
    player = msg["payload"]["name"]
    message = msg["payload"]["message"]
    session = msg["payload"]["uuid"]
    if session in clients.PlayerConnection.connections:
        log.debug(f'{msg["event"]} received for {player}@{session}')
        clients.PlayerConnection.connections[session].state["connected"] = False
        asyncio.create_task(messages_to_clients[session].put(Message(message, "IO")))


async def msg_player_session_command(msg):
    session = msg["payload"]["uuid"]
    command = msg["payload"]["command"]
    if session in clients.PlayerConnection.connections:
        if clients.PlayerConnection.connections[session].conn_type == "telnet":
            if command == "do echo":
                message = (WONT, ECHO)
            elif command == "dont echo":
                message = (WILL, ECHO)
            else:
                message = (WONT, ECHO)
            asyncio.create_task(messages_to_clients[session].put(Message(message, "COMMAND-TELNET")))


async def msg_game_softboot(msg):
    await softboot_game(msg["payload"]["wait_time"])


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
        asyncio.create_task(messages[msg["event"]](msg))
