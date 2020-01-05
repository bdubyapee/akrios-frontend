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

    ! Create an akrios_ca to use for the SSH portion of the front end.  You can use the command below to
    ! generate the file. Use a passphrase during ca generation, place it in keys.py.
    !
    ! ssh-keygen -f akrios_ca

    ! Create a key for the secure Telnet connectivity.
    ! openssl req -newkey rsa:2048 -nodes -keyout akrios.key -x509 -days 365 -out akrios.crt
"""

# Standard Lib
import asyncio
import logging
import signal
import ssl

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

    for each_task in tasks:
        each_task.cancel()

    log.info(f'Cancelling {len(tasks)} outstanding tasks')
    await asyncio.gather(*tasks, return_exceptions=True)
    loop_.stop()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for sig in signals:
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))

    telnet_port = 6969
    ssh_port = 7979
    ws_port = 8989

    # Set up our SSL context for Secure Telnet
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.check_hostname = False
    ssl_context.load_cert_chain('akrios.crt', 'akrios.key')

    log.info(f'Creating Telnet Listener on port {telnet_port}')
    log.info(f'Creating SSH Listener on port {ssh_port}')
    log.info(f'Creating Websocket Listener on port {ws_port}')
    all_servers = [telnetlib3.create_server(port=telnet_port,
                                            shell=client_telnetssh.handle_client,
                                            connect_maxwait=0.5,
                                            timeout=3600),
                   asyncssh.create_server(client_telnetssh.MySSHServer,
                                          '',
                                          ssh_port,
                                          server_host_keys=['akrios_ca'],
                                          passphrase=ca_phrase,
                                          process_factory=client_telnetssh.handle_client,
                                          keepalive_interval=10,
                                          login_timeout=3600),
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
