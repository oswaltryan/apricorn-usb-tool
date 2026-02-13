"""Unit tests for linux_usb module."""

from types import SimpleNamespace
from unittest.mock import patch
from usb_tool.backend.linux import LinuxBackend


def test_parse_lsblk_size_parses_various_units():
    """parse_lsblk_size must support several unit suffixes."""
    backend = LinuxBackend()
    assert backend.parse_lsblk_size("1G") == 1.0
    assert backend.parse_lsblk_size("1024M") == 1.0
    assert backend.parse_lsblk_size("1T") == 1024.0
    assert backend.parse_lsblk_size("1024K") == 1.0 / 1024
    assert backend.parse_lsblk_size("1E") == 1024**2
    assert backend.parse_lsblk_size("bogus") == 0.0


def test_list_usb_drives_parses_lsblk_output():
    """list_usb_drives should parse lsblk output into structured data."""
    lsblk_output = "/dev/sda SERIAL123 465G 1\n/dev/sdb SERIAL456 14T 0\n"
    mock_result = SimpleNamespace(returncode=0, stdout=lsblk_output, stderr="")

    with patch("subprocess.run", return_value=mock_result):
        backend = LinuxBackend()
        drives = backend.list_usb_drives()

    assert drives[0]["name"] == "/dev/sda"
    assert drives[0]["serial"] == "SERIAL123"
    assert drives[0]["mediaType"] == "Removable Media"
    assert drives[1]["mediaType"] == "Basic Disk"
    assert drives[1]["size_gb"] == 14 * 1024
