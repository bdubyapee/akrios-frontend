# -*- coding: utf-8 -*-

# Project: akrios_frontend
# Filename: protocols\mssp.py
#
# File Description: MSSP Support
#
# By: Jubelo
"""
    A very basic MSSP implementation.
"""

# Standard Library
import logging
from time import time
from typing import List

# Project

log: logging.Logger = logging.getLogger(__name__)

# MSSP Definitions
MSSP_VAR: bytes = bytes([1])
MSSP_VAL: bytes = bytes([2])

# MSSP Mud Protocol opcode
MSSP: bytes = bytes([70])  # MSSP Mud Protocol


def mssp_response() -> List:
    """
    The MSSP protocol contains the below possible values that are available to a player
    or "mud crawler".  Currently we just have dummy values for testing.  Once we have
    the game engine stable we will create status queries for some items and bring those in her
    as well.
    """
    mssp_values = {
        "NAME": "AkriosMUD",
        "PLAYERS": 3,
        "UPTIME": int(time()),
        "CODEBASE": "AkriosMUD",
        "CONTACT": "phippsb@gmail.com",
        "CRAWL DELAY": -1,
        "CREATED": 2002,
        "HOSTNAME": -1,
        "ICON": -1,
        "IP": -1,
        "IPV6": -1,
        "LANGUAGE": "English",
        "LOCATION": "United States of America",
        "MINIMUM AGE": -1,
        "PORT": [4000, 4001, 4002],
        "REFERRAL": -1,
        "WEBSITE": -1,
        "FAMILY": "Custom",
        "GENRE": "Fantasy",
        "GAMEPLAY": "Adventure",
        "STATUS": "Alpha",
        "GAMESYSTEM": "None",
        "INTERMUD": "Grapevine",
        "SUBGENRE": "High Fantasy",
        "AREAS": 1,
        "HELPFILES": 60,
        "MOBILES": 1,
        "OBJECTS": 1,
        "ROOMS": 20,
        "CLASSES": 5,
        "LEVELS": 50,
        "RACES": 5,
        "SKILLS": 1,
        "ANSI": 1,
        "MSP": 0,
        "UTF-8": 1,
        "VT100": 0,
        "XTERM 256 COLORS": 0,
        "XTERM TRUE COLORS": 0,
        "PAY TO PLAY": 0,
        "PAY FOR PERKS": 0,
        "HIRING BUILDERS": 0,
        "HIRING CODERS": 0
    }

    codes: List = [MSSP]

    for k, val in mssp_values.items():
        if isinstance(val, list):
            for each_val in val:
                codes.extend([MSSP_VAR, k.encode(), MSSP_VAL, each_val])
        else:
            codes.extend([MSSP_VAR, k.encode(), MSSP_VAL, val])

    return codes
