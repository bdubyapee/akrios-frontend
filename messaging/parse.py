# -*- coding: utf-8 -*-
# Project: akrios_frontend
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
import json
import logging
import subprocess
import time

# Project
from clients import clients
from keys import WS_SECRET
from protocols import telnet
from .messages import Message, messages_to_clients

# Third Party

log: logging.Logger = logging.getLogger(__name__)


async def softboot_game(wait_time):
    """
        The game has notified that it will shutdown.  We take the wait_time, sleep that amount of
        time and then launch the game.
    """
    await asyncio.sleep(wait_time)
    subprocess.Popen(
        ["python", "/home/bwp/PycharmProjects/akrios-ii/src/server.py"])


async def msg_heartbeat():
    """
        We have received a heartbeat from the game engine.  Right now we just log the receipt.
    """
    log.debug("parse.py:msg_heartbeat - Heartbeat received from game at: %s",
              time.time())


async def msg_players_output(payload):
    """
        The msg is output for a player.  We .put that message into the asyncio.queue for that
        specific player.
    """
    session = payload["uuid"]
    message = payload["message"]
    is_prompt = payload["is prompt"]

    if session in clients.connections:
        asyncio.create_task(messages_to_clients[session].put(
            Message("IO", message=message, is_prompt=is_prompt)))


async def msg_players_sign_in(payload):
    """
        We have received a successful player sign-in from the game engine.  We assign that
        authenticated name to the session.  Use for tracking during softboots.
    """
    player = payload["name"]
    session = payload["uuid"]
    if session in clients.connections:
        log.debug(
            "parse.py:msg_players_sign_in - players/sign-in received for %s@%s",
            player, session)
        clients.connections[session].name = player


async def msg_players_sign_out(payload):
    """
        We have received a player sign-out message from the engine.  This indicates a player has
        quit the game.  We change player session state to disconnected to end their session.
    """
    player = payload["name"]
    message = payload["message"]
    session = payload["uuid"]
    if session in clients.connections:
        log.debug(
            "parse.py:msg_players_sign_out - players/sign-out received for %s@%s",
            player, session)
        clients.connections[session].state["connected"] = False
        asyncio.create_task(messages_to_clients[session].put(
            Message("IO", message=message)))


async def msg_player_session_command(payload):
    """
        Any non standard I/O for a player session.

        Currently we use this non-I/O command to indicate to the player telnet client that it should
        or shouldn't echo locally at specific times (password entry).  Will expand in the future for
        SSH commands and Web Client.
    """
    session = payload["uuid"]
    command = payload["command"]
    if session in clients.connections and clients.connections[
            session].conn_type == "telnet":
        iac_cmd = b''
        if command == "dont echo":
            iac_cmd = telnet.echo_off()
        elif command == "do echo":
            iac_cmd = telnet.echo_on()

        asyncio.create_task(messages_to_clients[session].put(
            Message("COMMAND-TELNET", command=iac_cmd)))


async def msg_game_softboot(payload):
    """
        We have received a softboot message from the engine.  This indicates an administrator
        has issued the softboot command.  The game engine will handle saving and closing out
        players, we are now responsible for launching the game engine again.
    """
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
    """
        We have received a message from the game engine.  Verify we have the correct secret key.
        If the event is a key in the 'messages' dict above, we create a task to handle the message.
    """
    msg = json.loads(inp)

    if "secret" not in msg.keys() or msg["secret"] != WS_SECRET:
        log.warning("No secret in message header, or wrong key.")
        return

    if msg["event"] in messages:
        if payload := msg.get("payload"):
            asyncio.create_task(messages[str(msg["event"])](payload))
        else:
            asyncio.create_task(messages[str(msg["event"])]())
