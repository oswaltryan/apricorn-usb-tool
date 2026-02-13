import sys
from unittest.mock import patch

import pytest

from usb_tool import device_version
from usb_tool.backend.linux import LinuxBackend
from usb_tool.models import UsbDeviceInfo
from usb_tool.services import (
    VERSION_FIELD_NAMES,
    prune_hidden_version_fields,
    should_display_version_fields,
)


def _make_device(**overrides):
    data = {
        "bcdUSB": 3.2,
        "idVendor": "0984",
        "idProduct": "1407",
        "bcdDevice": "0502",
        "iManufacturer": "Apricorn",
        "iProduct": "Secure Key 3.0",
        "iSerial": "SER123",
        "SCSIDevice": False,
        "driveSizeGB": "16",
        "mediaType": "Basic Disk",
        "scbPartNumber": "12-3456",
        "hardwareVersion": "01",
        "modelID": "AA",
        "mcuFW": "1.2.3",
        "bridgeFW": "0502",
    }
    data.update(overrides)
    return UsbDeviceInfo(**data)


def test_should_display_version_fields_requires_non_na_scb_part():
    assert should_display_version_fields(_make_device(scbPartNumber="N/A")) is False


def test_should_display_version_fields_hides_on_bridge_mismatch():
    assert should_display_version_fields(_make_device(bridgeFW="0503")) is False


def test_should_display_version_fields_allows_matching_bridge_and_bcd():
    assert should_display_version_fields(_make_device(bridgeFW="0x502")) is True


def test_prune_hidden_version_fields_removes_all_version_keys_when_hidden():
    device = _make_device(bridgeFW="0503")
    prune_hidden_version_fields(device)
    serialized = device.to_dict()
    for name in VERSION_FIELD_NAMES:
        assert name not in serialized


def test_prune_hidden_version_fields_keeps_version_keys_when_visible():
    device = _make_device(bridgeFW="0502")
    prune_hidden_version_fields(device)
    serialized = device.to_dict()
    for name in VERSION_FIELD_NAMES:
        assert name in serialized


def test_linux_scan_hides_version_fields_when_bridge_mismatches_bcd():
    backend = LinuxBackend()
    lsblk_rows = [
        {
            "name": "/dev/sda",
            "serial": "SER123",
            "size_gb": 15.8,
            "mediaType": "Basic Disk",
        }
    ]
    lsusb_details = {
        "SER123": {
            "idVendor": "0984",
            "idProduct": "1407",
            "bcdUSB": "3.2",
            "bcdDevice": "0502",
            "iManufacturer": "Apricorn",
            "iProduct": "Secure Key 3.0",
        }
    }
    lshw_map = {"/dev/sda": {"serial": "SER123", "driver": "uas"}}

    with (
        patch.object(LinuxBackend, "_list_usb_drives", return_value=lsblk_rows),
        patch.object(LinuxBackend, "_get_lsusb_details", return_value=lsusb_details),
        patch.object(LinuxBackend, "_parse_uasp_info", return_value=lshw_map),
        patch(
            "usb_tool.backend.linux.populate_device_version",
            return_value={
                "scbPartNumber": "12-3456",
                "hardwareVersion": "01",
                "modelID": "AA",
                "mcuFW": "1.2.3",
                "bridgeFW": "0503",
            },
        ),
    ):
        devices = backend.scan_devices()

    assert len(devices) == 1
    serialized = devices[0].to_dict()
    for name in VERSION_FIELD_NAMES:
        assert name not in serialized


def test_linux_scan_keeps_version_fields_when_bridge_matches_bcd():
    backend = LinuxBackend()
    lsblk_rows = [
        {
            "name": "/dev/sda",
            "serial": "SER123",
            "size_gb": 15.8,
            "mediaType": "Basic Disk",
        }
    ]
    lsusb_details = {
        "SER123": {
            "idVendor": "0984",
            "idProduct": "1407",
            "bcdUSB": "3.2",
            "bcdDevice": "0502",
            "iManufacturer": "Apricorn",
            "iProduct": "Secure Key 3.0",
        }
    }
    lshw_map = {"/dev/sda": {"serial": "SER123", "driver": "uas"}}

    with (
        patch.object(LinuxBackend, "_list_usb_drives", return_value=lsblk_rows),
        patch.object(LinuxBackend, "_get_lsusb_details", return_value=lsusb_details),
        patch.object(LinuxBackend, "_parse_uasp_info", return_value=lshw_map),
        patch(
            "usb_tool.backend.linux.populate_device_version",
            return_value={
                "scbPartNumber": "12-3456",
                "hardwareVersion": "01",
                "modelID": "AA",
                "mcuFW": "1.2.3",
                "bridgeFW": "0502",
            },
        ),
    ):
        devices = backend.scan_devices()

    assert len(devices) == 1
    serialized = devices[0].to_dict()
    for name in VERSION_FIELD_NAMES:
        assert name in serialized


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific path format")
def test_windows_read_buffer_uses_device_namespace_path(monkeypatch):
    captured = {}

    def _fake_create_file(path, *_args):
        captured["path"] = path
        return device_version.INVALID_HANDLE_VALUE

    monkeypatch.setattr(
        device_version.ctypes.windll.kernel32, "CreateFileW", _fake_create_file
    )
    monkeypatch.setattr(
        device_version.ctypes, "GetLastError", lambda: device_version.errno.EACCES
    )

    with pytest.raises(PermissionError):
        device_version._windows_read_buffer(4)

    assert captured["path"] == r"\\.\PhysicalDrive4"
