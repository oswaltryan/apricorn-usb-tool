# tests/test_mac_usb.py

import json
from types import SimpleNamespace
from unittest.mock import patch
from usb_tool import mac_usb


def test_list_usb_drives_filters_apricorn_devices():
    """list_usb_drives should return devices matching ID OR Manufacturer."""
    profiler_data = {
        "SPUSBDataType": [
            {
                "_name": "Root",
                "_items": [
                    # Matches via Manufacturer
                    {
                        "manufacturer": "Apricorn",
                        "vendor_id": "0x0000",
                        "serial_num": "XYZ",
                    },
                    # Matches via Vendor ID
                    {
                        "manufacturer": "Generic",
                        "vendor_id": "0x0984",
                        "serial_num": "123",
                    },
                ],
            },
            {
                "_name": "Root",
                "_items": [
                    # Should not match
                    {
                        "manufacturer": "Other",
                        "vendor_id": "0x1111",
                        "serial_num": "ABC",
                    }
                ],
            },
        ]
    }

    # Mock must include returncode to pass the check in list_usb_drives
    mock_result = SimpleNamespace(returncode=0, stdout=json.dumps(profiler_data))

    with patch("subprocess.run", return_value=mock_result):
        drives = mac_usb.list_usb_drives()

    # Should find both the Apricorn manufacturer and the 0984 vendor
    assert len(drives) == 2


def test_parse_uasp_info_builds_boolean_map():
    """parse_uasp_info should create a mapping of device names to UAS usage."""

    # 1. Setup mock data for system_profiler (the first call)
    profiler_json = json.dumps(
        {
            "SPUSBDataType": [
                {
                    "_name": "Drive One",
                    "vendor_id": "0984",
                    "Media": [{"bsd_name": "disk2s1"}],
                }
            ]
        }
    )

    # 2. Setup mock data for diskutil (the second call)
    diskutil_out = "Protocol: USB\nTransport: UAS"

    # 3. Create a side_effect function to handle different commands
    def mock_subprocess_run(cmd, **kwargs):
        # Handle system_profiler call
        if "system_profiler" in cmd:
            return SimpleNamespace(returncode=0, stdout=profiler_json)

        # Handle diskutil call
        if "diskutil" in cmd:
            return SimpleNamespace(returncode=0, stdout=diskutil_out)

        return SimpleNamespace(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        uas_dict = mac_usb.parse_uasp_info()

    assert "Drive One" in uas_dict
    assert uas_dict["Drive One"] is True
