# -*- coding: utf-8 -*-
# Project: akrios-frontend
# Filename: frontend.py
#
# File Description: Main launching point for the connection front end to Akrios-II.
#
# By: Jubelo
"""
    Front End utilized for separating server(connectivity) and game logic for Akrios-II.
    The end game of this front end is to have several client connection options available (Telnet, Secure Telnet,
    SSH and Web Client)/

    Currently we handle Telnet, Secure Telnet and SSH clients.

    Allows for game to initiate a "softboot", which shuts down the game engine itself and instructs
    this front end to run a new instance.  We provide the client session -> player name details to the
    new game engine instance which automatically logs in the players.

    SSH Details
    ! Create an akrios_ca to use for the SSH portion of the front end.  You can use the command below to
    ! generate the file. Use a passphrase during ca generation, place it in keys.py.
    !
    ! ssh-keygen -t rsa -b 4096 -o -a 100

    A portion of the Secure (SSL/TLS) Telnet code was lifted from https://github.com/zapstar
    I do not see any licensing information on his project so placing credit here.

    Secure Telnet Details
    ! Create Certificate and key for SSL context (Secure Telnet)
    !
    ! openssl req -newkey rsa:2048 -new -nodes -x509 -days 3650 -keyout server_key.pem -out server_cert.pem
"""

# Standard Library
import argparse
import asyncio
import logging
import signal
import ssl
from time import time
# import uvloop  # Future

# Third Party
import asyncssh
import telnetlib3
import websockets

# Project
import clients
from keys import passphrase as ca_phrase
import servers
import statistics

# asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())  # Future


async def shutdown(signal_, loop_):
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.

        https://www.roguelynn.com/talks/
    """
    log.warning(f"frontend.py:shutdown - Received exit signal {signal_.name}")

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    log.info(f"frontend.py:shutdown - Cancelling {len(tasks)} outstanding tasks")

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    log.warning(f"frontend.py:shutdown - Exceptions: {exceptions}")
    loop_.stop()


def handle_exceptions(loop_, context):
    """
        We attach this as the exception handler to the event loop.  Currently we just
        log, as warnings, any exceptions caught.
    """
    msg = context.get("exception", context["message"])
    log.warning(f"frontend.py:handle_exceptions - Caught exception: {msg} in loop: {loop_}")
    log.warning(f"frontend.py:handle_exceptions - Caught in task: {asyncio.current_task()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Change the option prefix characters",
        prefix_chars="-+/",
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
    parser.add_argument('-st', action="store_false",
                        default=None,
                        help='Disable Secure Telnet listener',
                        )
    parser.add_argument('-tp', action="store",
                        default=4000,
                        help='Telnet Listener Port (Default: 4000)',
                        type=int,
                        )
    parser.add_argument('-sp', action="store",
                        default=4001,
                        help='SSH Listener Port (Default: 4001)',
                        type=int,
                        )
    parser.add_argument('-stp', action="store",
                        default=4002,
                        help='Secure Telnet Listener Port (Default: 4002)',
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
    log = logging.getLogger(__name__)

    all_servers = []

    if not args.t:
        telnet_port = args.tp
        log.info(f"frontend.py:__main__ - Creating client Telnet listener on port {telnet_port}")
        all_servers.append(telnetlib3.create_server(
            host="localhost",
            port=telnet_port,
            shell=clients.client_telnet_handler,
            connect_maxwait=0.5,
            timeout=3600,
            log=log,))

    if not args.s:
        ssh_port = args.sp
        log.info(f"frontend.py:__main__ - Creating client SSH listener on port {ssh_port}")
        all_servers.append(asyncssh.create_server(
            clients.MySSHServer,
            "",
            ssh_port,
            server_host_keys=["akrios_ca"],
            passphrase=ca_phrase,
            process_factory=clients.client_ssh_handler,
            keepalive_interval=10,
            login_timeout=3600,))

    if not args.st:
        st_port = args.stp
        log.info(f"frontend.py:__main__ - Creating client Secure Telnet listener on port {st_port}")

        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.options |= ssl.OP_SINGLE_DH_USE
        ssl_ctx.options |= ssl.OP_SINGLE_ECDH_USE
        ssl_ctx.load_cert_chain("server_cert.pem", keyfile="server_key.pem")
        ssl_ctx.check_hostname = False
        # ssl_ctx.verify_mode = ssl.VerifyMode.CERT_REQUIRED
        ssl_ctx.set_ciphers("ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384")
        secure_telnet = asyncio.start_server(clients.client_stp_handler,
                                             "localhost",
                                             st_port,
                                             ssl=ssl_ctx,
                                             ssl_handshake_timeout=5.0)
        all_servers.append(secure_telnet)

    ws_port = args.wsp
    log.info(f"frontend.py:__main__ - Creating game engine websocket listener on port {ws_port}")
    all_servers.append(websockets.serve(servers.ws_handler, "localhost", ws_port))

    log.info("frontend.py:__main__ - Launching game front end loop:\n\r")

    statistics.startup_time = int(time())

    loop = asyncio.get_event_loop()

    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig, loop)))

    loop.set_exception_handler(handle_exceptions)

    for server in all_servers:
        loop.run_until_complete(server)

    loop.run_forever()

    log.info("frontend.py:__main__ - Front end shut down.")
