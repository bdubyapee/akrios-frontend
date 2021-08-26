# -*- coding: utf-8 -*-
# Project: akrios_frontend
# Filename: frontend.py
#
# File Description: Main launching point for the connection front end to Akrios-II.
#
# By: Jubelo
"""
    Front End utilized for separating server(connectivity) and game logic for Akrios-II.
    The purpose of this front end is to have several client connection options available (Telnet,
    Secure Telnet, SSH and Web Client)

    Currently we handle Telnet, Secure Telnet and SSH clients.

    Allows for the game to initiate a "softboot", which shuts down the game engine itself and
    instructs this front end to run a new instance.  We provide the client session -> player name
    details to the new game engine instance which automatically logs in the players.

    There will need to be an SSH key created for SSH as well as a Certificate pair for the telnet
    over TLS features.  Please reference the readme.md for details on creating those locally
    for testing.
"""

# Standard Library
import argparse
import asyncio
import logging
import signal
import ssl

# Third Party
import asyncssh
import telnetlib3
import websockets

# Project
from clients import clients
from servers import servers
from keys import PASSPHRASE


async def shutdown(signal_, loop_):
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.

        https://www.roguelynn.com/talks/
    """
    log.warning("frontend.py:shutdown - Received exit signal %s", signal_.name)

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    log.info("frontend.py:shutdown - Cancelling %s outstanding tasks",
             len(tasks))

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    log.warning("frontend.py:shutdown - Exceptions: %s", exceptions)
    loop_.stop()


def handle_exceptions(loop_, context):
    """
        We attach this as the exception handler to the event loop.  Currently we just
        log, as warnings, any exceptions caught.
    """
    msg = context.get("exception", context["message"])
    log.warning(
        "frontend.py:handle_exceptions - Caught exception: %s in loop: %s",
        msg, loop_)
    log.warning("frontend.py:handle_exceptions - Caught in task: %s",
                asyncio.current_task())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Change the option prefix characters",
        prefix_chars="-+/",
    )

    parser.add_argument(
        '-d',
        action="store_true",
        default=None,
        help='Set log level to debug',
    )
    parser.add_argument(
        '-t',
        action="store_false",
        default=None,
        help='Disable Telnet listener',
    )
    parser.add_argument(
        '-s',
        action="store_false",
        default=None,
        help='Disable SSH listener',
    )
    parser.add_argument(
        '-st',
        action="store_false",
        default=None,
        help='Disable Secure Telnet listener',
    )
    parser.add_argument(
        '-tp',
        action="store",
        default=4000,
        help='Telnet Listener Port (Default: 4000)',
        type=int,
    )
    parser.add_argument(
        '-sp',
        action="store",
        default=4001,
        help='SSH Listener Port (Default: 4001)',
        type=int,
    )
    parser.add_argument(
        '-stp',
        action="store",
        default=4002,
        help='Secure Telnet Listener Port (Default: 4002)',
        type=int,
    )
    parser.add_argument('-wsp',
                        action="store",
                        default=8989,
                        help='Websocket Listener Port (Default:8989)',
                        type=int)
    args = parser.parse_args()

    LOG_LEVEL = logging.DEBUG if args.d else logging.INFO

    logging.basicConfig(
        format="%(asctime)s: %(name)s - %(levelname)s - %(message)s",
        level=LOG_LEVEL)
    log = logging.getLogger(__name__)

    all_servers = []

    if not args.t:
        telnet_port = args.tp
        log.info(
            "frontend.py:__main__ - Creating client Telnet listener on port %s",
            telnet_port)
        all_servers.append(
            telnetlib3.create_server(
                host="localhost",
                port=telnet_port,
                shell=clients.client_telnet_handler,
                connect_maxwait=0.5,
                timeout=3600,
                log=log,
            ))

    if not args.s:
        ssh_port = args.sp
        log.info(
            "frontend.py:__main__ - Creating client SSH listener on port %s",
            ssh_port)
        all_servers.append(
            asyncssh.create_server(
                clients.MySSHServer,
                "",
                ssh_port,
                server_host_keys=["akrios_ca"],
                passphrase=PASSPHRASE,
                process_factory=clients.client_ssh_handler,
                keepalive_interval=10,
                login_timeout=3600,
            ))

    if not args.st:
        st_port = args.stp
        log.info(
            "frontend.py:__main__ - Creating client Secure Telnet listener on port %s",
            st_port)

        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.options |= ssl.OP_SINGLE_DH_USE
        ssl_ctx.options |= ssl.OP_SINGLE_ECDH_USE
        ssl_ctx.load_cert_chain("server_cert.pem", keyfile="server_key.pem")
        ssl_ctx.check_hostname = False
        # ssl_ctx.verify_mode = ssl.VerifyMode.CERT_REQUIRED
        ssl_ctx.set_ciphers(
            "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384")
        secure_telnet = asyncio.start_server(clients.client_stp_handler,
                                             "localhost",
                                             st_port,
                                             ssl=ssl_ctx,
                                             ssl_handshake_timeout=5.0)
        all_servers.append(secure_telnet)

    ws_port = args.wsp
    log.info(
        "frontend.py:__main__ - Creating game engine websocket listener on port %s",
        ws_port)
    all_servers.append(
        websockets.serve(servers.ws_handler, "localhost", ws_port))

    log.info("frontend.py:__main__ - Launching game front end loop:\n\r")

    loop = asyncio.get_event_loop()

    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(sig, loop)))

    loop.set_exception_handler(handle_exceptions)

    for server in all_servers:
        loop.run_until_complete(server)

    loop.run_forever()

    log.info("frontend.py:__main__ - Front end shut down.")
