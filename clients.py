# -*- coding: utf-8 -*-
# Project: akrios_frontend
# Filename: clients.py
#
# File Description: Client connections via Telnet, Secure Telnet and SSH.
#
# By: Jubelo
"""
    Housing the Class(es) and coroutines for accepting and maintaining connections from clients
    via Telnet, Secure Telnet and SSH.
"""

# Standard Library
import asyncio
import json
import logging
from uuid import uuid4

# Third Party
import asyncssh

# Project
from keys import WS_SECRET
from messages import Message, messages_to_clients, messages_to_game
from protocols import telnet

log = logging.getLogger(__name__)

connections = {}


class PlayerConnection:
    """
        Each connection when created in async handle_client will instantiate this class.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
            self.state is the current state of the client connection
            self.name is any authenticated player name associated with this session
                Currently used for "softboot" capability
            self.uuid is a str(uuid.uuid4()) for unique session tracking
    """
    def __init__(self, addr, port, conn_type, rows=24):
        self.addr = addr
        self.port = port
        self.rows = rows
        self.conn_type = conn_type
        self.state = {"connected": True, "logged in": False}
        self.name = ""
        self.uuid = str(uuid4())

    async def notify_connected(self):
        """
            Create JSON message to notify the game engine of a new client connection.
            Put this message into the messages_to_game asyncio.Queue().
        """
        payload = {
            "uuid": self.uuid,
            "addr": self.addr,
            "port": self.port,
            "rows": self.rows,
        }
        msg = {
            "event": "connection/connected",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(
                Message("IO",
                        message=json.dumps(msg, sort_keys=True, indent=4))))

    async def notify_disconnected(self):
        """
            Create JSON Payload to notify the game engine of a client disconnect.
            Put this message into the messages_to_game asyncio.Queue().
        """
        payload = {
            "uuid": self.uuid,
            "addr": self.addr,
            "port": self.port,
        }
        msg = {
            "event": "connection/disconnected",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(
                Message("IO",
                        message=json.dumps(msg, sort_keys=True, indent=4))))


class MySSHServer(asyncssh.SSHServer):
    """
    This class facilitates allowing SSH access in without requiring "ssh" credentials.  The
    various methods are configured to allow the "unauthenticated" access as well as some logging.

    XXX Clean this up and document it.  Came from the asyncssh docs somewhere.
    """
    def connection_made(self, conn):
        log.info("clients.py:MySShServer - SSH connection received from %s",
                 conn.get_extra_info("peername")[0])

    def connection_lost(self, exc):
        if exc:
            log.warning("clients.py:MySShServer - SSH connection error: %s",
                        str(exc))
        else:
            log.info("clients.py:MySShServer - SSH connection closed.")

    def begin_auth(self, username):
        return False

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return True


async def register_client(connection):
    """
        Upon a new client connection, we register it to the connections dict.
    """
    connections[connection.uuid] = connection
    messages_to_clients[connection.uuid] = asyncio.Queue()

    await connection.notify_connected()


async def unregister_client(connection):
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    if connection.uuid in connections:
        connections.pop(connection.uuid)
        messages_to_clients.pop(connection.uuid)

        await connection.notify_disconnected()


async def client_read(reader, connection):
    """
        Utilized by the Telnet and SSH client_handlers.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We first await control back to the loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and put into the
            messages_to_game asyncio.Queue()
    """
    while connection.state["connected"]:
        inp = await reader.readline()
        log.info("Raw received data in client_read : %s", inp)

        if not inp:  # This is an EOF.  Hard disconnect.
            connection.state["connected"] = False
            return

        payload = {
            "uuid": connection.uuid,
            "addr": connection.addr,
            "port": connection.port,
            "msg": inp.strip(),
        }
        msg = {
            "event": "player/input",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(
                Message("IO",
                        message=json.dumps(msg, sort_keys=True, indent=4))))


async def client_stp_read(reader, writer, connection):
    """
        Utilized by the Secure Telnet client_stp_handler.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We first await control back to the loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and put into the
            messages_to_game asyncio.Queue()
    """
    while connection.state["connected"]:
        inp = await reader.readline()

        if not inp:
            log.info('Connection terminated with %s', connection.addr)
            connection.state["connected"] = False

        if inp.startswith(telnet.IAC):
            opcodes, inp = telnet.split_opcode_from_input(inp)
            await telnet.handle(opcodes, writer)
        else:
            inp = inp.decode()

        payload = {
            "uuid": connection.uuid,
            "addr": connection.addr,
            "port": connection.port,
            "msg": inp.strip(),
        }
        msg = {
            "event": "player/input",
            "secret": WS_SECRET,
            "payload": payload,
        }

        asyncio.create_task(
            messages_to_game.put(
                Message("IO",
                        message=json.dumps(msg, sort_keys=True, indent=4))))


async def client_write(writer, connection):
    """
        Utilized by the Telnet and SSH client_handlers.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We await for any messages from the game to this client, then write and drain it.
    """
    while connection.state["connected"]:
        msg_obj = await messages_to_clients[connection.uuid].get()
        if msg_obj.is_io:
            writer.write(msg_obj.msg)
            if msg_obj.is_prompt:
                writer.write(telnet.go_ahead())
        elif msg_obj.is_command_telnet:
            writer.write(telnet.iac([msg_obj.command]))

        asyncio.create_task(writer.drain())


async def client_stp_write(writer, connection):
    """
        Utilized by the Secure Telnet client_stp_handler.  We have some bytes/str work to deal with
        so it's probably easier to have this as a separate coroutine from the other. We want this
        coroutine to run while the client is connected, so we begin with a while loop.  We await
        for any messages from the game to this client, then write and drain it.
    """
    while connection.state["connected"]:
        msg_obj = await messages_to_clients[connection.uuid].get()
        if msg_obj.is_io:
            writer.write(msg_obj.msg.encode())
            if msg_obj.is_prompt:
                writer.write(telnet.go_ahead())

        asyncio.create_task(writer.drain())


async def client_ssh_handler(process):
    """
    This handler is for SSH client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    log.debug("clients.py:client_ssh_handler - SSH details are: %s",
              dir(process))
    reader = process.stdin
    writer = process.stdout
    client_details = process.get_extra_info("peername")

    addr, port, *rest = client_details
    log.info("Connection established with %s : %s: %s", addr, port, rest)

    connection = PlayerConnection(addr, port, "ssh")

    await register_client(connection)

    tasks = [
        asyncio.create_task(client_read(reader, connection),
                            name=f"{connection.uuid} ssh read"),
        asyncio.create_task(client_write(writer, connection),
                            name=f"{connection.uuid} ssh write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} ssh handler")

    # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
    # of execution or an exception.  If either the read or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    _, rest = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

    # Once we reach this point one of our tasks (reader/writer) have completed or failed.  Remove
    # client from the registration list and perform connection specific cleanup.
    await unregister_client(connection)

    process.close()
    process.exit(0)

    for task in rest:
        task.cancel()


async def client_telnet_handler(reader, writer):
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    log.debug("clients.py:client_telnet_handler - telnet details are: %s",
              dir(reader))
    client_details = writer.get_extra_info("peername")

    addr, port, *rest = client_details
    log.info("Connection established with %s : %s : %s", addr, port, rest)

    # Need to work on better telnet support for regular old telnet clients.
    # Everything so far works great in Mudlet.  Just saying....

    connection = PlayerConnection(addr, port, "telnet")

    await register_client(connection)

    tasks = [
        asyncio.create_task(client_read(reader, connection),
                            name=f"{connection.uuid} telnet read"),
        asyncio.create_task(client_write(writer, connection),
                            name=f"{connection.uuid} telnet write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} ssh handler")

    # We send an IAC+WONT+ECHO to the client so that it locally echo's it's own input.
    writer.write(telnet.echo_on())

    # Advertise to the client that we will do features we are capable of.
    writer.write(telnet.advertise_features())

    await writer.drain()

    # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
    # of execution or an exception.  If either the reader or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    _, rest = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

    # Once we reach this point one of our tasks (reader/writer) have completed or failed.
    # Remove client from the registration list and perform connection specific cleanup.
    await unregister_client(connection)

    writer.write_eof()
    await writer.drain()
    writer.close()

    for task in rest:
        task.cancel()


async def client_stp_handler(reader, writer):
    """
    This handler is for secure telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    log.debug("clients.py:client_stp_handler - secure telnet details are: %s",
              dir(reader))
    client_details = writer.get_extra_info("peername")

    addr, port, *rest = client_details
    log.info("Connection established with %s : %s : %s", addr, port, rest)

    connection = PlayerConnection(addr, port, "secure telnet")

    await register_client(connection)

    tasks = [
        asyncio.create_task(client_stp_read(reader, writer, connection),
                            name=f"{connection.uuid} stp read"),
        asyncio.create_task(client_stp_write(writer, connection),
                            name=f"{connection.uuid} stp write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} stp handler")

    # We send an IAC+WONT+ECHO to the client so that it locally echo's it's own input.
    writer.write(telnet.echo_on())

    # Advertise to the client that we will do features we are capable of.
    writer.write(telnet.advertise_features())

    await writer.drain()

    # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
    # of execution or an exception.  If either the reader or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    _, rest = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

    # Once we reach this point one of our tasks (reader/writer) have completed or failed.
    # Remove client from the registration list and perform connection specific cleanup.
    await unregister_client(connection)

    await writer.drain()
    writer.close()

    for task in rest:
        task.cancel()
