#! usr/bin/env python
# Project: akrios-fe
# Filename: main.py
#
# File Description: Main launching point for the connection front end to Akrios.
#
# By: Jubelo
"""
    Front End utilized for separating server(connectivity) and game logic for Akrios.
    End game is to have several front ends available (Telnet, Secure Telnet, SSH, Web, etc)

    Currently we handle telnet and SSH clients.

    Allows for game to initiate a "softboot", which shuts down the game engine itself and instructs
    this front end to run a new instance.  We provide the client session -> player name details to the
    new game engine instance which automatically logs in the players.

    SSH Details
    ! Create an akrios_ca to use for the SSH portion of the front end.  You can use the command below to
    ! generate the file. Use a passphrase during ca generation, place it in keys.py.
    !
    ! ssh-keygen -t rsa -b 4096 -o -a 100
"""

# Standard Library
import argparse
import asyncio
import logging
import signal

# Standard Library Typing
from typing import Awaitable, Dict, List

# Third Party
import asyncssh  # type: ignore
import telnetlib3  # type: ignore
import websockets

# Project
import clients
from keys import passphrase as ca_phrase
import servers


async def shutdown(signal_: signal.Signals, loop_: asyncio.AbstractEventLoop) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in __main__

        https://www.roguelynn.com/talks/
    """
    log.warning(f"Received exit signal {signal_.name}")

    tasks: List[asyncio.Task] = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    log.info(f"Cancelling {len(tasks)} outstanding tasks")

    for each_task in tasks:
        each_task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    loop_.stop()


def handle_exception_generic(loop_: asyncio.AbstractEventLoop, context: Dict) -> None:
    msg: str = context.get("exception", context["message"])
    log.warning(f"Caught exception: {msg} in loop: {loop_}")
    log.warning(f"Caught in task: {asyncio.current_task().get_name()}")  # type: ignore


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Change the option prefix characters',
        prefix_chars='-+/',
    )

    parser.add_argument('-d', action="store_true",
                        default=None,
                        help='Set log level to debug',
                        )
    parser.add_argument('-t', action="store_false",
                        default=None,
                        help='Disable Telnet listener',
                        )
    parser.add_argument('-s', action="store_false",
                        default=None,
                        help='Disable SSH listener',
                        )
    parser.add_argument('-tp', action="store",
                        default=6969,
                        help='Telnet Listener Port (Default: 6969)',
                        type=int,
                        )
    parser.add_argument('-sp', action="store",
                        default=7979,
                        help='SSH Listener Port (Default: 7979)',
                        type=int,
                        )
    parser.add_argument('-wsp', action="store",
                        default=8989,
                        help='Websocket Listener Port (Default:8989)',
                        type=int
                        )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.d else logging.INFO

    logging.basicConfig(format="%(asctime)s: %(name)s - %(levelname)s - %(message)s", level=log_level)
    log: logging.Logger = logging.getLogger(__name__)

    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig, loop)))

    loop.set_exception_handler(handle_exception_generic)

    all_servers: List[Awaitable] = []

    if not args.t:
        telnet_port: int = args.tp
        log.info(f"Creating client Telnet listener on port {telnet_port}")
        all_servers.append(telnetlib3.create_server(
            port=telnet_port,
            shell=clients.client_telnet_handler,
            connect_maxwait=0.5,
            timeout=3600,
            log=log,))

    if not args.s:
        ssh_port: int = args.sp
        log.info(f"Creating client SSH listener on port {ssh_port}")
        all_servers.append(asyncssh.create_server(
            clients.MySSHServer,
            "",
            ssh_port,
            server_host_keys=["akrios_ca"],
            passphrase=ca_phrase,
            process_factory=clients.client_ssh_handler,
            keepalive_interval=10,
            login_timeout=3600,))

    ws_port: int = args.wsp
    log.info(f"Creating game engine websocket listener on port {ws_port}")
    all_servers.append(websockets.serve(servers.ws_handler, "localhost", ws_port))

    log.info("Launching game front end loop:\n\r")

    for each_server in all_servers:
        loop.run_until_complete(each_server)

    loop.run_forever()

    log.info("Front end shut down.")
    loop.close()
