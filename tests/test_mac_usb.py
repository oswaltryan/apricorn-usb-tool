"""Unit tests for mac_usb module.

These tests emphasize clear behavior of parsing helpers.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import usb_tool.mac_usb as mac_usb


# ---------------------------
# Utility Function Tests
# ---------------------------

def test_bytes_to_gb_converts_bytes_to_gigabytes():
    """Confirm basic byte-to-GB conversion."""
    assert mac_usb.bytes_to_gb(1024 ** 3) == 1.0


def test_parse_lsblk_size_understands_units():
    """parse_lsblk_size should interpret standard units."""
    assert mac_usb.parse_lsblk_size("1G") == 1.0
    assert mac_usb.parse_lsblk_size("1024M") == 1.0
    assert mac_usb.parse_lsblk_size("1T") == 1024.0
    assert mac_usb.parse_lsblk_size("invalid") == 0.0


def test_find_closest_picks_nearest_value():
    """find_closest returns the option nearest to the target."""
    assert mac_usb.find_closest(9, [1, 10, 20]) == 10


# ---------------------------
# system_profiler Parsing Tests
# ---------------------------

def test_list_usb_drives_filters_apricorn_devices():
    """list_usb_drives should return only Apricorn devices."""
    profiler_data = {
        "SPUSBDataType": [
            {
                "_name": "Root",
                "another": "value",
                "_items": [
                    {"manufacturer": "Apricorn", "Media": {}, "serial_num": "XYZ"}
                ],
            },
            {
                "_name": "Root",
                "_items": [{"manufacturer": "SomeoneElse", "Media": {}, "serial_num": "ABC"}],
            },
        ]
    }
    mock_result = SimpleNamespace(returncode=0, stdout=json.dumps(profiler_data))

    with patch("usb_tool.mac_usb.subprocess.run", return_value=mock_result):
        drives = mac_usb.list_usb_drives()

    assert len(drives) == 1
    assert drives[0]["manufacturer"] == "Apricorn"


def test_parse_uasp_info_builds_boolean_map():
    """parse_uasp_info should create a mapping of device names to UAS usage."""
    uasp_output = "Drive One: UAS\nDrive Two: Not UAS\n"
    mock_result = SimpleNamespace(stdout=uasp_output)

    with patch("usb_tool.mac_usb.subprocess.run", return_value=mock_result):
        uas_dict = mac_usb.parse_uasp_info()

    assert uas_dict == {"Drive One": True, "Drive Two": False}
