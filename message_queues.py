#! usr/bin/env python
# Project: akrios-fe
# Filename: message_queues.py
#
# File Description: Message queues for passing input and output between the game and clients.
#
# By: Jubelo
"""
    Housing the message queues.
"""

import asyncio

messages_to_game = asyncio.Queue()
messages_to_clients = {}
