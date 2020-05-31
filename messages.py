#! usr/bin/env python
# Project: akrios-frontend
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

# Third Party

# Project

# There is only one game connection, create a asyncio.Queue to hold messages to the game from clients.
messages_to_game = asyncio.Queue()

# There will be multiple clients connected.  uuid of client will be key, values will be an asyncio.Queue.
messages_to_clients = {}


class Message(object):
    def __init__(self, msg_type, msg="", command=(b'', b''), is_prompt=""):
        self.msg = msg
        if is_prompt == "true":
            self.is_prompt = True
        else:
            self.is_prompt = False
        self.command = command
        if msg_type in ["IO", "COMMAND-TELNET", "COMMAND-SSH"]:
            self.msg_type = msg_type

    @property
    def is_command_telnet(self):
        return True if self.msg_type == "COMMAND-TELNET" else False

    @property
    def is_command_ssh(self):
        return True if self.msg_type == "COMMAND-SSH" else False

    @property
    def is_io(self):
        return True if self.msg_type == "IO" else False
