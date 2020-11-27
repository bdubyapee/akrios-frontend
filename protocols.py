#! usr/bin/env python
# Project: akrios-frontend
# Filename: protocols.py
#
# File Description: Consolidate various protocols.
#
# By: Jubelo
"""
    Housing various Telnet elements and MUD protocols.  I don't believe we really need
    to go full blown Telnet with all capabilities.  We'll try and create a useful subset
    of the protocol useful for MUDs.  We will also add in various MUD protocols.
"""

# Standard Library
import asyncio
import logging

# Third Party

# Project


log: logging.Logger = logging.getLogger(__name__)


# Telnet protocol characters
IAC = bytes([255])  # "Interpret As Command"
DONT = bytes([254])
DO = bytes([253])
WONT = bytes([252])
WILL = bytes([251])
SB = bytes([250])  # Subnegotiation Begin
GA = bytes([249])  # Go Ahead
SE = bytes([240])  # Subnegotiation End
MSSP = bytes([70])  # MSSP Mud Protocol
CHARSET = bytes([42])  # CHARSET
NAWS = bytes([31])  # window size
EOR = bytes([25])  # end or record
TTYPE = bytes([24])  # terminal type
ECHO = bytes([1])  # echo
theNULL = bytes([0])

# Telnet protocol by codes
code = {'IAC':     bytes([255]),
        'DONT':    bytes([254]),
        'DO':      bytes([253]),
        'WONT':    bytes([252]),
        'WILL':    bytes([251]),
        'SB':      bytes([250]),
        'GA':      bytes([249]),
        'SE':      bytes([240]),
        'MSSP':    bytes([70]),
        'CHARSET': bytes([42]),
        'NAWS':    bytes([31]),
        'EOR':     bytes([25]),
        'TTYPE':   bytes([24]),
        'ECHO':    bytes([1]),
        'theNull': bytes([0])}

# Telnet protocol by bytes
code_by_byte = {v: k for k, v in code.items()}


# MSSP Definitions
MSSP_VAR = 1
MSSP_VAL = 2

# Game capabilities to advertise
GAME_CAPABILITIES = ['MSSP', 'NAWS']


# Utility functions
def iac(codes):
    """
    Used to build commands on the fly.
    """
    command = ""
    for each_code in codes:
        command = f"{command}{each_code}"

    return f"{IAC}{command}"


def decode(data):
    log.info(f"Received raw data of: {data}")
    decoded = []
    for each_code in range(len(data)-1):
        decoded.append(code_by_byte[each_code])
    log.info(f"Received: {' '.join(decoded)}")


def advertise_features():
    features = ""
    for each_feature in GAME_CAPABILITIES:
        features = f"{features}{IAC}{WILL}{code[each_feature]}"


def echo_off():
    return f"{IAC}{WILL}{ECHO}"


def echo_on():
    return f"{IAC}{WONT}{ECHO}"


def ga():
    return f"{IAC}{GA}"
