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
import logging
from string import printable
# Third Party

# Project
import statistics

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

# Telnet protocol by string designators
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

# Telnet protocol, int representation as key, string designator value.
code_by_byte = {ord(v): k for k, v in code.items()}


# MSSP Definitions
MSSP_VAR = "1"
MSSP_VAL = "2"

# Game capabilities to advertise
GAME_CAPABILITIES = ['MSSP']


# Utility functions
def iac(codes):
    """
    Used to build commands on the fly.
    """
    command = b""
    for each_code in codes:
        if type(each_code) == str:
            command += each_code.encode()
        elif type(each_code) == int:
            command += str(each_code).encode()
        else:
            command += each_code

    return IAC+command


def iac_sb(codes):
    """
    Used to build Sub-Negotiation commands on the fly.
    """
    command = [b""]
    for each_code in codes:
        if type(each_code) == str:
            command.append(each_code.encode())
        elif type(each_code) == int:
            command.append(str(each_code).encode())
        else:
            command.append(each_code)
    command.append(b"")
    command = b' '.join(command)

    return IAC + SB + command + IAC + SE


def split_opcode_from_input(data):
    """
    This one will need some love once we get into subnegotiation, ie NAWS.
    """
    log.info(f"Received raw data (len={len(data)}) of: {data}")
    opcodes = b''
    inp = ''
    for each_code in range(len(data)):
        if data[each_code] in code_by_byte:
            opcodes += bytes([data[each_code]])
        elif chr(data[each_code]) in printable:
            inp += chr(data[each_code])
    log.info(f"Bytecodes found in input.\n\ropcodes: {opcodes}\n\rinput returned: {inp}")
    return opcodes, inp


def advertise_features():
    features = b""
    for each_feature in GAME_CAPABILITIES:
        features += features+IAC+WILL+code[each_feature]
    log.info(f"Advertising features: {features}")
    return features


def echo_off():
    return IAC+WILL+ECHO


def echo_on():
    return IAC+WONT+ECHO


def ga():
    return IAC+GA


# Opcode operations functions.
def do_mssp():
    startup_time = statistics.startup_time
    count = statistics.player_count
    name = statistics.mud_name.encode()
    output = iac_sb([MSSP,
                     MSSP_VAR, "PLAYERS".encode(), MSSP_VAL, count,
                     MSSP_VAR, "UPTIME".encode(), MSSP_VAL, startup_time,
                     MSSP_VAR, "NAME".encode(), MSSP_VAL, name])

    return output


# Define a dictionary of responses to various received opcodes.
opcode_match = {DO + MSSP: do_mssp}

# Future.
main_negotiations = (WILL, WONT, DO, DONT)


# Primary function for decoding and handling received opcodes.
async def handle(opcodes, connection, writer):
    codes = opcodes.split(IAC)
    for each_code in codes:
        if each_code and each_code in opcode_match:
            result = opcode_match[each_code]()
            log.info(f"Responding to previous opcode with: {result}")
            writer.write(result)
            await writer.drain()
