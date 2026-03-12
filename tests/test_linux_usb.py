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


def test_scan_devices_populates_driver_transport_from_usb_serial():
    with (
        patch.object(
            LinuxBackend,
            "_parse_uasp_info",
            return_value={"/dev/sdb": {"serial": "SERIAL123"}},
        ),
        patch.object(
            LinuxBackend,
            "_list_usb_drives",
            return_value=[
                {
                    "name": "/dev/sdb",
                    "serial": "SERIAL123",
                    "size_gb": 64.0,
                    "mediaType": "Removable Media",
                }
            ],
        ),
        patch.object(
            LinuxBackend,
            "_get_lsusb_details",
            return_value={
                "SERIAL123": {
                    "idVendor": "0984",
                    "idProduct": "1407",
                    "bcdUSB": "3.0",
                    "bcdDevice": "0300",
                    "iManufacturer": "Apricorn",
                    "iProduct": "Secure Key 3.0",
                }
            },
        ),
        patch.object(
            LinuxBackend,
            "_get_transport_map_by_serial",
            return_value={"SERIAL123": "UAS"},
        ),
        patch.object(
            LinuxBackend,
            "_get_transport_map",
            return_value={"/dev/sdb": "Unknown"},
        ),
        patch("usb_tool.backend.linux.populate_device_version", return_value={}),
    ):
        backend = LinuxBackend()
        devices = backend.scan_devices()

    assert len(devices) == 1
    serialized = devices[0].to_dict()
    assert serialized["driverTransport"] == "UAS"


def test_get_udev_usb_driver_parses_usb_storage_driver():
    mock_result = SimpleNamespace(
        returncode=0,
        stdout="E: ID_USB_DRIVER=usb-storage\n",
        stderr="",
    )

    with patch("usb_tool.backend.linux.subprocess.run", return_value=mock_result):
        backend = LinuxBackend()
        driver = backend._get_udev_usb_driver("/dev/sda")

    assert driver == "usb-storage"


def test_get_transport_map_classifies_udev_driver():
    with patch.object(
        LinuxBackend,
        "_get_udev_usb_driver",
        side_effect=["usb-storage", "uas", ""],
    ):
        backend = LinuxBackend()
        transport_map = backend._get_transport_map(["/dev/sda", "/dev/sdb", "/dev/sdc"])

    assert transport_map == {
        "/dev/sda": "BOT",
        "/dev/sdb": "UAS",
        "/dev/sdc": "Unknown",
    }


def test_get_transport_map_by_serial_parses_usb_devices_output():
    usb_devices_output = """
T:  Bus=04 Lev=01 Prnt=01 Port=00 Cnt=01 Dev#=  8 Spd=5000 MxCh= 0
S:  Manufacturer=Apricorn
S:  Product=Secure Key 3.0
S:  SerialNumber=000000000001
I:  If#= 0 Alt= 1 #EPs= 4 Cls=08(stor.) Sub=06 Prot=62 Driver=uas

T:  Bus=04 Lev=01 Prnt=01 Port=00 Cnt=01 Dev#=  7 Spd=5000 MxCh= 0
S:  Manufacturer=Apricorn
S:  Product=Fortress
S:  SerialNumber=101300032245
I:  If#= 0 Alt= 0 #EPs= 2 Cls=08(stor.) Sub=06 Prot=50 Driver=usb-storage
"""
    mock_result = SimpleNamespace(returncode=0, stdout=usb_devices_output, stderr="")

    with patch("usb_tool.backend.linux.subprocess.run", return_value=mock_result):
        backend = LinuxBackend()
        transport_map = backend._get_transport_map_by_serial()

    assert transport_map == {
        "000000000001": "UAS",
        "101300032245": "BOT",
    }
