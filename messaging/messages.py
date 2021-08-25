# -*- coding: utf-8 -*-
# Project: akrios_frontend
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

# There is only one game connection, create a asyncio.Queue to hold messages to the game from
# clients.
messages_to_game = asyncio.Queue()

# There will be multiple clients connected.  uuid of client will be key, values will be an
# asyncio.Queue.
messages_to_clients = {}


class Message:
    """
    A Message is specifically a message meant for a connected client.
    """
    def __init__(self, msg_type, **kwargs):
        self.msg = kwargs['message']
        self.command = kwargs.get('command', None)
        self.prompt = kwargs.get('is_prompt', "false")
        if msg_type in ["IO", "COMMAND-TELNET", "COMMAND-SSH"]:
            self.msg_type = msg_type

    @property
    def is_command_telnet(self):
        """
        A shortcut property to determine if this message is a Telnet Opcode.
        """
        return self.msg_type == "COMMAND-TELNET"

    @property
    def is_command_ssh(self):
        """
        A shortcut property to determine if this message is a special SSH command.
        """
        return self.msg_type == "COMMAND-SSH"

    @property
    def is_io(self):
        """
        A shortcut property to determine if this message is normal I/O.
        """
        return self.msg_type == "IO"

    @property
    def is_prompt(self):
        """
        A shortcut property to determine if this message is a prompt (versus normal I/O).
        """
        return self.prompt == "true"
