"""Unit tests for linux_usb module.

These tests focus on pure functions and parsing logic.
"""

from types import SimpleNamespace
from unittest.mock import patch

import usb_tool.linux_usb as linux_usb


# ---------------------------
# Utility Function Tests
# ---------------------------

def test_bytes_to_gb_handles_invalid_input():
    """bytes_to_gb should gracefully handle invalid values."""
    assert linux_usb.bytes_to_gb(1024 ** 3) == 1.0
    assert linux_usb.bytes_to_gb(-1) == 0.0
    assert linux_usb.bytes_to_gb("bad") == 0.0


def test_parse_lsblk_size_parses_various_units():
    """parse_lsblk_size must support several unit suffixes."""
    assert linux_usb.parse_lsblk_size("1G") == 1.0
    assert linux_usb.parse_lsblk_size("1024M") == 1.0
    assert linux_usb.parse_lsblk_size("1T") == 1024.0
    assert linux_usb.parse_lsblk_size("1024K") == 1.0 / 1024
    assert linux_usb.parse_lsblk_size("1E") == 1024**2
    assert linux_usb.parse_lsblk_size("bogus") == 0.0


def test_find_closest_handles_edge_cases():
    """find_closest should return None for invalid input."""
    assert linux_usb.find_closest(4, [1, 5, 7]) == 5
    assert linux_usb.find_closest(-1, [1, 2]) is None
    assert linux_usb.find_closest(4, []) is None


# ---------------------------
# lsblk Parsing Tests
# ---------------------------

def test_list_usb_drives_parses_lsblk_output():
    """list_usb_drives should parse lsblk output into structured data."""
    lsblk_output = "/dev/sda SERIAL123 465G 1\n/dev/sdb SERIAL456 14T 0\n"
    mock_result = SimpleNamespace(returncode=0, stdout=lsblk_output, stderr="")

    with patch("usb_tool.linux_usb.subprocess.run", return_value=mock_result):
        drives = linux_usb.list_usb_drives()

    assert drives[0]["name"] == "/dev/sda"
    assert drives[0]["serial"] == "SERIAL123"
    assert drives[0]["mediaType"] == "Removable Media"
    assert drives[1]["mediaType"] == "Basic Disk"
    assert drives[1]["size_gb"] == 14 * 1024
