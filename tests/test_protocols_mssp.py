# -*- coding: utf-8 -*-

# Project: akrios_frontend
# Filename: tests\test_protocol_mssp.py
#
# File Description: Test suite for the mssp protocol module.
#
# By: Jubelo
"""
    Tests for the MSSP protocol module.
"""

# Standard Library
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Third Party

# Project
from protocols.mssp import mssp_response  # noqa


def test_mssp_response_length():
    assert len(mssp_response()) == 181


def test_mssp_response_return_type():
    assert type(mssp_response()) == list


def test_mssp_response_basic_contents():
    assert b'NAME' in mssp_response()
