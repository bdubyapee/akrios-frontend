#! usr/bin/env python
# Project: akrios-fe
# Filename: clients.py
#
# File Description: Client connections via Telnet and SSH.
#
# By: Jubelo
"""
    Housing the Class(es) and coroutines for accepting and maintaining connections from clients via Telnet
    and SSH.
"""

# Standard Library
import asyncio
import json
import logging
from uuid import uuid4

# Standard Library Typing
from typing import Any, Dict, List

# Third Party
import asyncssh  # type: ignore
from telnetlib3 import WONT, ECHO  # type: ignore

# Project
from messages import Message, messages_to_clients, messages_to_game
from keys import WS_SECRET

log: logging.Logger = logging.getLogger(__name__)


class PlayerConnection(object):
    """
        Each connection when created in async handle_client will instance this.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
            self.state is the current state of the client connection
            self.name is any authenticated player name associated with this session
                Currently used for "softboot" capability
            self.uuid is a str(uuid.uuid4()) for unique session tracking
    """
    def __init__(self, addr: str, port: str, conn_type: str) -> None:
        self.addr: str = addr
        self.port: str = port
        self.conn_type: str = conn_type
        self.state: Dict[str, bool] = {"connected": True, "logged in": False}
        self.name: str = ""
        self.uuid: str = str(uuid4())

    async def notify_connected(self) -> None:
        """
            Create JSON message to notify the game engine of a new client connection.
            Put this message into the messages_to_game asyncio.Queue().
        """
        payload: Dict[str, str] = {
            "uuid": self.uuid,
            "addr": self.addr,
            "port": self.port,
        }
        msg: Dict[str, Any] = {
            "event": "connection/connected",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(Message(json.dumps(msg, sort_keys=True, indent=4), "IO"))
        )

    async def notify_disconnected(self) -> None:
        """
            Create JSON Payload to notify the game engine of a client disconnect.
            Put this message into the messages_to_game asyncio.Queue().
        """
        payload: Dict[str, str] = {
            "uuid": self.uuid,
            "addr": self.addr,
            "port": self.port,
        }
        msg: Dict[str, Any] = {
            "event": "connection/disconnected",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(Message(json.dumps(msg, sort_keys=True, indent=4), "IO"))
        )


class MySSHServer(asyncssh.SSHServer):
    """
    This class facilitates allowing SSH access in without requiring credentials.  The various methods
    are configured to allow the "unauthenticated" access as well as some logging.

    XXX Clean this up and document it.  Came from the asyncssh docs somewhere.
    """

    def connection_made(self, conn):
        log.info(f'SSH connection received from {conn.get_extra_info("peername")[0]}')

    def connection_lost(self, exc):
        if exc:
            log.warning(f"SSH connection error: {str(exc)}")
        else:
            log.info("SSH connection closed.")

    def begin_auth(self, username):
        return False

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return True


connections: Dict[str, PlayerConnection] = {}


async def register_client(connection: PlayerConnection) -> None:
    """
        Upon a new client connection, we register it to the connections dict.
    """
    connections[connection.uuid] = connection
    messages_to_clients[connection.uuid] = asyncio.Queue()

    await connection.notify_connected()


async def unregister_client(connection: PlayerConnection) -> None:
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    if connection.uuid in connections:
        connections.pop(connection.uuid)
        messages_to_clients.pop(connection.uuid)

        await connection.notify_disconnected()


async def client_read(reader, connection) -> None:
    """
        Utilized by the client_handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We first await control back to the loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and put into the
            messages_to_game asyncio.Queue()
    """
    while connection.state["connected"]:
        inp: str = await reader.readline()

        if not inp:  # This is an EOF.  Hard disconnect.
            connection.state["connected"] = False
            return

        payload: Dict[str, str] = {
            "uuid": connection.uuid,
            "addr": connection.addr,
            "port": connection.port,
            "msg": inp.strip(),
        }
        msg: Dict[str, Any] = {
            "event": "player/input",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(Message(json.dumps(msg, sort_keys=True, indent=4), "IO"))
        )


async def client_write(writer, connection) -> None:
    """
        Utilized by the client_handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We await for any messages from the game to this client, then write and drain it.
    """
    while connection.state["connected"]:
        msg_obj = await messages_to_clients[connection.uuid].get()
        if msg_obj.is_io:
            writer.write(msg_obj.msg)
        elif msg_obj.is_command_telnet:
            writer.iac(msg_obj.msg[0], msg_obj.msg[1])

        asyncio.create_task(writer.drain())


async def client_handler(*args) -> None:
    """
    This is a generic handler/"shell".  It is called on new connections of both
    telnet and SSH clients.

    By performing the if/else blocks we can handle both Telnet and SSH
    connections via the same handler.

    This can probably be cleaner by checking the type of the positional arguments.
    Or perhaps break it into two handlers anyway.  Investigate this.
    """
    if len(args) == 1:
        conn_type = "ssh"
        process = args[0]
        log.debug(f"SSH details are: {dir(process)}")
        reader = process.stdin
        writer = process.stdout
        addr, port = process.get_extra_info("peername")
    else:
        conn_type = "telnet"
        process = None
        reader = args[0]
        writer = args[1]
        addr, port = writer.get_extra_info("peername")

        # Need to work on slightly better telnet support for regular old telnet clients.
        # Everything so far works great in Mudlet.  Just saying....
        # We sent an IAC+WONT+ECHO to the client so that it locally echo's it's own input.
        writer.iac(WONT, ECHO)

    connection: PlayerConnection = PlayerConnection(addr, port, conn_type)

    await register_client(connection)

    tasks: List[asyncio.Task] = [
        asyncio.create_task(client_read(reader, connection), name=f"{connection.uuid} read"),
        asyncio.create_task(client_write(writer, connection), name=f"{connection.uuid} write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} handler")  # type: ignore

    # We want to .wait until the first task is completed.  Completed could be an actual finishing
    # of execution or an exception.  If either the read or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    _, rest = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

    await unregister_client(connection)

    if conn_type == "ssh":
        process.close()
        process.exit(0)
    elif conn_type == "telnet":
        writer.write_eof()
        writer.close()

    for each_task in rest:
        each_task.cancel()
