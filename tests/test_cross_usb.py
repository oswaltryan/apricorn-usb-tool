import json
from types import SimpleNamespace
import pytest
from usb_tool import cross_usb
import sys


def test_parse_poke_targets_handles_indices_and_paths():
    # This test is now platform-aware
    if sys.platform == "win32":
        # On Windows, devices have 'physicalDriveNum'
        devices = [
            SimpleNamespace(physicalDriveNum=0, driveSizeGB=1),
            SimpleNamespace(physicalDriveNum=1, driveSizeGB=2),
        ]
        # On Windows, we test targeting by index number
        poke_input = "1,2"
        expected_targets = {("#1", 0), ("#2", 1)}
    elif sys.platform == "linux":
        # On Linux, devices have 'blockDevice'
        devices = [
            SimpleNamespace(blockDevice="/dev/sda", driveSizeGB=1),
            SimpleNamespace(blockDevice="/dev/sdb", driveSizeGB=2),
        ]
        # On Linux, we test targeting by both index and path
        poke_input = "1,/dev/sdb"
        expected_targets = {("#1", "/dev/sda"), ("/dev/sdb", "/dev/sdb")}
    elif sys.platform == "darwin":
        # On macOS, devices have 'blockDevice'
        devices = [
            SimpleNamespace(blockDevice="/dev/disk2", driveSizeGB=1),
            SimpleNamespace(blockDevice="/dev/disk3", driveSizeGB=2),
        ]
        # On macOS, we test targeting by index number
        poke_input = "1,2"
        expected_targets = {("#1", "/dev/disk2"), ("#2", "/dev/disk3")}
    else:
        # Default case for other OSes, though the test will likely fail
        devices = []
        poke_input = ""
        expected_targets = set()

    targets, skipped = cross_usb._parse_poke_targets(poke_input, devices)

    # Use a set for comparison as the order is not guaranteed
    assert set(targets) == expected_targets
    assert skipped == []


def test_parse_poke_targets_rejects_invalid_values():
    devices = [SimpleNamespace(blockDevice="/dev/sda", driveSizeGB=1)]
    with pytest.raises(ValueError):
        cross_usb._parse_poke_targets("3", devices)


def test_handle_list_action_json_output(capfd):
    device = SimpleNamespace(
        physicalDriveNum=2,
        blockDevice="/dev/disk3",
        driveSizeGB=64,
        iSerial="XYZ123",
    )
    cross_usb._handle_list_action([device], json_mode=True)
    captured = capfd.readouterr()
    payload = json.loads(captured.out)
    assert "devices" in payload
    assert len(payload["devices"]) == 1
    device_block = payload["devices"][0]
    assert "1" in device_block
    device_entry = device_block["1"]
    assert device_entry["iSerial"] == "XYZ123"
    assert device_entry["driveSizeGB"] == 64
    assert device_entry["physicalDriveNum"] == 2
    assert captured.err == ""
