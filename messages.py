#! usr/bin/env python
# Project: akrios-fe
# Filename: messages.py
#
# File Description: Message queues for passing input and output between the game and clients.
#
# By: Jubelo
"""
    Housing the message queues and one Class to facilitate commands between the game
    engine and front end.
"""

# Standard Library
import asyncio

# Standard Library Typing
from typing import ByteString, Dict, Tuple

# Third Party

# Project

# There is only one game connection, create a asyncio.Queue to hold messages to the game from clients.
messages_to_game: asyncio.Queue = asyncio.Queue()

# There will be multiple clients connected.  uuid of client will be key, values will be an asyncio.Queue.
messages_to_clients: Dict[str, asyncio.Queue] = {}


class Message(object):
    def __init__(self, msg_type: str, msg: str = "", command: Tuple[ByteString, ByteString] = (b'', b'')) -> None:
        self.msg = msg
        self.command = command
        if msg_type in ["IO", "COMMAND-TELNET", "COMMAND-SSH"]:
            self.msg_type = msg_type

    @property
    def is_command_telnet(self) -> bool:
        return True if self.msg_type == "COMMAND-TELNET" else False

    @property
    def is_command_ssh(self) -> bool:
        return True if self.msg_type == "COMMAND-SSH" else False

    @property
    def is_io(self) -> bool:
        return True if self.msg_type == "IO" else False
