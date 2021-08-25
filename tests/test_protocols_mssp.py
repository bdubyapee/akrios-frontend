# -*- coding: utf-8 -*-

# Project: akrios-frontend
# Filename: tests\test_protocol_mssp.py
#
# File Description: Test suite for the mssp protocol module.
#
# By: Jubelo
"""
    Tests for the MSSP protocol module.
"""

# Standard Library

# Third Party

# Project
from protocols.mssp import mssp_response


def test_mssp_response_length():
    assert len(mssp_response()) == 181


def test_mssp_response_return_type():
    assert type(mssp_response()) == list


def test_mssp_response_basic_contents():
    assert b'NAME' in mssp_response()
