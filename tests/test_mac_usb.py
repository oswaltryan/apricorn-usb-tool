# tests/test_mac_usb.py

import json
from types import SimpleNamespace
from unittest.mock import patch
from usb_tool.backend.macos import MacOSBackend


def test_list_usb_drives_filters_apricorn_devices():
    profiler_data = {
        "SPUSBDataType": [
            {
                "_name": "Root",
                "_items": [
                    {
                        "manufacturer": "Apricorn",
                        "vendor_id": "0x0000",
                        "serial_num": "XYZ",
                    },
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
                    {
                        "manufacturer": "Other",
                        "vendor_id": "0x1111",
                        "serial_num": "ABC",
                    }
                ],
            },
        ]
    }
    mock_result = SimpleNamespace(returncode=0, stdout=json.dumps(profiler_data))

    with patch("subprocess.run", return_value=mock_result):
        backend = MacOSBackend()
        drives = backend.list_usb_drives()

    assert len(drives) == 2


def test_parse_uasp_info_builds_boolean_map():
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
    diskutil_out = "Protocol: USB\nTransport: UAS"

    def mock_subprocess_run(cmd, **kwargs):
        if "system_profiler" in cmd:
            return SimpleNamespace(returncode=0, stdout=profiler_json)
        if "diskutil" in cmd:
            return SimpleNamespace(returncode=0, stdout=diskutil_out)
        return SimpleNamespace(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        backend = MacOSBackend()
        # Note: parse_uasp_info now takes 'drives' argument in the new backend
        # We need to feed it the drives list that list_usb_drives would produce
        drives = backend.list_usb_drives()
        uas_dict = backend.parse_uasp_info(drives)

    assert "Drive One" in uas_dict
    assert uas_dict["Drive One"] is True


def test_find_apricorn_device_skips_excluded_pids():
    drives = [
        {
            "_name": "Bad Apricorn",
            "manufacturer": "Apricorn",
            "vendor_id": "0x0984",
            "product_id": "0x0221",
            "serial_num": "BAD1",
            "Media": [{"size_in_bytes": 100 * 1024**3, "bsd_name": "disk3s1"}],
        },
        {
            "_name": "Good Apricorn",
            "manufacturer": "Apricorn",
            "vendor_id": "0x0984",
            "product_id": "0x1234",
            "serial_num": "GOOD1",
            "Media": [{"size_in_bytes": 100 * 1024**3, "bsd_name": "disk4s1"}],
        },
    ]

    with (
        patch.object(MacOSBackend, "_list_usb_drives", return_value=drives),
        patch.object(MacOSBackend, "_parse_uasp_info", return_value={}),
    ):
        backend = MacOSBackend()
        result = backend.scan_devices()

    assert result and len(result) == 1
    assert result[0].idProduct == "1234"
