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
    ! ssh-keygen -f akrios_ca
"""

# Standard Lib
import asyncio
import logging
import signal

# Third Party
import asyncssh
import telnetlib3
import websockets

# Project
import clients
from keys import passphrase as ca_phrase
import servers

logging.basicConfig(
    format="%(asctime)s: %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)


async def shutdown(signal_, loop_):
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in __main__

        https://www.roguelynn.com/talks/
    """
    log.warning(f"Received exit signal {signal_.name}")

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    for each_task in tasks:
        each_task.cancel()

    log.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop_.stop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for sig in signals:
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(s, loop))
        )

    telnet_port = 6969
    ssh_port = 7979
    ws_port = 8989

    log.info(f"Creating Telnet Listener on port {telnet_port}")
    log.info(f"Creating SSH Listener on port {ssh_port}")
    log.info(f"Creating Websocket Listener on port {ws_port}")
    all_servers = [
        telnetlib3.create_server(
            port=telnet_port,
            shell=clients.client_handler,
            connect_maxwait=0.5,
            timeout=3600,
            log=log,
        ),
        asyncssh.create_server(
            clients.MySSHServer,
            "",
            ssh_port,
            server_host_keys=["akrios_ca"],
            passphrase=ca_phrase,
            process_factory=clients.client_handler,
            keepalive_interval=10,
            login_timeout=3600,
        ),
        websockets.serve(servers.ws_handler, "localhost", ws_port),
    ]

    log.info("Launching game front end loop:\n\r")

    for each_server in all_servers:
        loop.run_until_complete(each_server)

    try:
        loop.run_forever()
    except Exception as err:
        log.warning(f"Error in main loop: {err}")

    log.info("Front end shut down.")
    loop.close()
