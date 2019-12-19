#! usr/bin/env python
# Project: akrios-fe
# Filename: main.py
# 
# File Description: Main launching point for the connection front end to Akrios.
# 
# By: Jubelo
"""
    Initial test of separating server(Socket) and game logic for Akrios.
    End game is to have several front ends available (Telnet, Secure Telnet, SSH, Web, etc)
    Should also allow to have connections stay up while restarting game
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
import client_telnetssh
from keys import passphrase as ca_phrase
import server_ws

logging.basicConfig(format='%(asctime)s: %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
log = logging.getLogger(__name__)


async def shutdown(signal_, loop_):
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in __main__

        Courtesy of the great "talks" by Lynn Root
        https://www.roguelynn.com/talks/
    """
    log.warning(f'Received exit signal {signal_.name}')

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    log.info(f'Cancelling {len(tasks)} outstanding tasks')
    await asyncio.gather(*tasks, return_exceptions=True)
    loop_.stop()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    to_game_queue = []

    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for sig in signals:
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))

    telnet_port = 6969
    ssh_port = 7979
    ws_port = 8989

    log.info(f'Creating Telnet Listener on port {telnet_port}')
    log.info(f'Creating SSH Listener on port {ssh_port}')
    log.info(f'Creating Websocket Listener on port {ws_port}')
    all_servers = [telnetlib3.create_server(port=telnet_port,
                                            shell=client_telnetssh.handle_client,
                                            connect_maxwait=0.5),
                   asyncssh.create_server(client_telnetssh.MySSHServer,
                                          '',
                                          ssh_port,
                                          server_host_keys=['akrios_ca'],
                                          passphrase=ca_phrase,
                                          process_factory=client_telnetssh.handle_client),
                   websockets.serve(server_ws.ws_handler,
                                    'localhost',
                                    ws_port)
                   ]

    log.info('Launching game front end loop:\n\r')

    for each_server in all_servers:
        loop.run_until_complete(each_server)

    try:
        loop.run_forever()
    except Exception as err:
        log.warning(f'Error in main loop: {err}')

    log.info('Front end shut down.')
    loop.close()
