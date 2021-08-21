# -*- coding: utf-8 -*-

# Project: akrios-frontend
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

# Third Party

# Project
import statistics

log: logging.Logger = logging.getLogger(__name__)

# MSSP Definitions
MSSP_VAR = bytes([1])
MSSP_VAL = bytes([2])

# MSSP Mud Protocol opcode
MSSP = bytes([70])  # MSSP Mud Protocol


def mssp_response():
    mssp_values = {"NAME": statistics.mud_name,
                   "PLAYERS": statistics.player_count,
                   "UPTIME": statistics.startup_time,
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
                   # "MINIMUM AGE": -1,
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

    codes = [MSSP]

    for k, v in mssp_values.items():
        if type(v) == list:
            for each_val in v:
                codes.extend([MSSP_VAR, k.encode(), MSSP_VAL, each_val])
        else:
            codes.extend([MSSP_VAR, k.encode(), MSSP_VAL, v])

    return codes
