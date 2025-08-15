from types import SimpleNamespace
import pytest
from usb_tool import cross_usb


def test_parse_poke_targets_handles_indices_and_paths():
    devices = [
        SimpleNamespace(blockDevice="/dev/sda", driveSizeGB=1),
        SimpleNamespace(blockDevice="/dev/sdb", driveSizeGB=2),
    ]
    targets, skipped = cross_usb._parse_poke_targets("1,/dev/sdb", devices)
    assert ("#1", "/dev/sda") in targets
    assert ("/dev/sdb", "/dev/sdb") in targets
    assert skipped == []


def test_parse_poke_targets_rejects_invalid_values():
    devices = [SimpleNamespace(blockDevice="/dev/sda", driveSizeGB=1)]
    with pytest.raises(ValueError):
        cross_usb._parse_poke_targets("3", devices)
