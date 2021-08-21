# -*- coding: utf-8 -*-

# Project: akrios-frontend
# Filename: telnet.py
#
# File Description: Consolidate various protocols.
#
# By: Jubelo
"""
    Housing various Telnet elements and MUD protocols.  I don't believe we really need
    to go full blown Telnet with all capabilities.  We'll try and create a useful subset
    of the protocol useful for MUDs.
"""

# Standard Library
import logging
from string import printable
# Third Party

# Project
import mssp

log: logging.Logger = logging.getLogger(__name__)


# Basic Telnet protocol opcodes. The MSSP character will be imported from it's module.
IAC = bytes([255])  # "Interpret As Command"
DONT = bytes([254])
DO = bytes([253])
WONT = bytes([252])
WILL = bytes([251])
SB = bytes([250])  # Subnegotiation Begin
GA = bytes([249])  # Go Ahead
SE = bytes([240])  # Subnegotiation End
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

# Game capabilities to advertise
GAME_CAPABILITIES = ['MSSP']


# Utility functions
def iac(codes):
    """
    Used to build commands on the fly.
    """
    command = []

    for each_code in codes:
        if type(each_code) == str:
            command.append(each_code.encode())
        elif type(each_code) == int:
            command.append(str(each_code).encode())
        else:
            command.append(each_code)

    command = b''.join(command)

    return IAC+command


def iac_sb(codes):
    """
    Used to build Sub-Negotiation commands on the fly.
    """
    command = []

    for each_code in codes:
        if type(each_code) == str:
            command.append(each_code.encode())
        elif type(each_code) == int:
            command.append(str(each_code).encode())
        else:
            command.append(each_code)

    command = b''.join(command)

    return IAC + SB + command + IAC + SE


def split_opcode_from_input(data):
    """
    This one will need some love once we get into sub negotiation, ie NAWS.
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
    """
    Build and return a byte string of the features we are capable of and want to
    advertise to the connecting client.
    """
    features = b""
    for each_feature in GAME_CAPABILITIES:
        features += features+IAC+WILL+code[each_feature]
    log.info(f"Advertising features: {features}")
    return features


def echo_off():
    """
    Return the Telnet opcode for IAC WILL ECHO.
    """
    return IAC+WILL+ECHO


def echo_on():
    """
    Return the Telnet opcode for IAC WONT ECHO.
    """
    return IAC+WONT+ECHO


def ga():
    """
    Return the Telnet opcode for IAC GA (Go Ahead) which some clients want to
    see after each prompt so that they know we are done sending this particular block
    of text o them.
    """
    return IAC+GA


# Define a dictionary of responses to various received opcodes.
opcode_match = {DO + mssp.MSSP: mssp.mssp_response}

# Future.
main_negotiations = (WILL, WONT, DO, DONT)


# Primary function for decoding and handling received opcodes.
async def handle(opcodes, connection, writer):
    """
    This is the handler for opcodes we receive from the connected client.
    """
    for each_code in opcodes.split(IAC):
        if each_code and each_code in opcode_match:
            result = iac_sb(opcode_match[each_code]())
            log.info(f"Responding to previous opcode with: {result}")
            writer.write(result)
            await writer.drain()
