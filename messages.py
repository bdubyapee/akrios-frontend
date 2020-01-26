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

# Third Party

# Project

messages_to_game = asyncio.Queue()
messages_to_clients = {}


class Message(object):
    def __init__(self, msg, msg_type):
        self.msg = msg
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
