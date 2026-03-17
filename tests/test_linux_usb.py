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
    lsblk_output = "/dev/sda SERIAL123 465G 1 0\n/dev/sdb SERIAL456 14T 0 1\n"
    mock_result = SimpleNamespace(returncode=0, stdout=lsblk_output, stderr="")

    with patch("subprocess.run", return_value=mock_result):
        backend = LinuxBackend()
        drives = backend.list_usb_drives()

    assert drives[0]["name"] == "/dev/sda"
    assert drives[0]["serial"] == "SERIAL123"
    assert drives[0]["mediaType"] == "Removable Media"
    assert drives[0]["readOnly"] is False
    assert drives[1]["mediaType"] == "Basic Disk"
    assert drives[1]["size_gb"] == 14 * 1024
    assert drives[1]["readOnly"] is True


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
                    "readOnly": False,
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
            "_get_udev_info_map",
            return_value={
                "/dev/sdb": {
                    "ID_USB_DRIVER": "uas",
                    "ID_PATH": "pci-0000:00:14.0-usb-0:1:1.0-scsi-0:0:0:0",
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
        patch.object(
            LinuxBackend,
            "_get_controller_map",
            return_value={"/dev/sdb": "Intel"},
        ),
        patch("usb_tool.backend.linux.populate_device_version", return_value={}),
    ):
        backend = LinuxBackend()
        devices = backend.scan_devices()

    assert len(devices) == 1
    serialized = devices[0].to_dict()
    assert serialized["driverTransport"] == "UAS"
    assert serialized["usbController"] == "Intel"
    assert serialized["readOnly"] is False


def test_scan_devices_emits_profile_output_when_enabled(capsys):
    with (
        patch.object(LinuxBackend, "_parse_uasp_info", return_value={}),
        patch.object(LinuxBackend, "_list_usb_drives", return_value=[]),
        patch.object(LinuxBackend, "_get_udev_info_map", return_value={}),
        patch.object(LinuxBackend, "_get_transport_map_by_serial", return_value={}),
        patch.object(LinuxBackend, "_get_transport_map", return_value={}),
        patch.object(LinuxBackend, "_get_controller_map", return_value={}),
        patch.object(LinuxBackend, "_get_lsusb_details", return_value={}),
    ):
        backend = LinuxBackend()
        devices = backend.scan_devices(profile_scan=True)

    captured = capsys.readouterr()
    assert devices == []
    assert "linux-scan-profile details:" in captured.err
    assert "populate_device_version_total=0.00ms" in captured.err
    assert "device_count=0" in captured.err
    assert "linux-scan-profile expanded=false" in captured.err
    assert "lshw_uasp=" in captured.err
    assert "device_build=" in captured.err
    assert "total=" in captured.err


def test_scan_devices_profile_details_precede_summary(capsys):
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
                    "readOnly": False,
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
        patch.object(LinuxBackend, "_get_udev_info_map", return_value={"/dev/sdb": {}}),
        patch.object(
            LinuxBackend,
            "_get_transport_map_by_serial",
            return_value={"SERIAL123": "UAS"},
        ),
        patch.object(
            LinuxBackend, "_get_transport_map", return_value={"/dev/sdb": "UAS"}
        ),
        patch.object(
            LinuxBackend,
            "_get_controller_map",
            return_value={"/dev/sdb": "Intel"},
        ),
        patch.object(
            LinuxBackend,
            "_timed_populate_device_version",
            return_value={"_profile_ms": 12.34},
        ),
    ):
        backend = LinuxBackend()
        devices = backend.scan_devices(profile_scan=True)

    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(devices) == 1
    assert lines[0].startswith("linux-scan-profile details:")
    assert "populate_device_version_total=12.34ms" in lines[0]
    assert "device_count=1" in lines[0]
    assert lines[1].startswith("linux-scan-profile expanded=false")
    assert "lsblk_drives=1" in lines[1]
    assert "udev_nodes=1" in lines[1]
    assert "transport_serials=1" in lines[1]
    assert "lsusb_devices=1" in lines[1]
    assert "devices=1" in lines[1]
    assert "lshw_uasp=" in lines[1]
    assert "transport_by_serial=" in lines[1]
    assert "controller_map=" in lines[1]


def test_get_udev_info_parses_usb_storage_driver():
    mock_result = SimpleNamespace(
        returncode=0,
        stdout=(
            "E: ID_USB_DRIVER=usb-storage\n"
            "E: ID_PATH=pci-0000:00:14.0-usb-0:1:1.0-scsi-0:0:0:0\n"
        ),
        stderr="",
    )

    with patch("usb_tool.backend.linux.subprocess.run", return_value=mock_result):
        backend = LinuxBackend()
        info = backend._get_udev_info("/dev/sda")

    assert info["ID_USB_DRIVER"] == "usb-storage"
    assert info["ID_PATH"] == "pci-0000:00:14.0-usb-0:1:1.0-scsi-0:0:0:0"


def test_get_transport_map_classifies_udev_driver():
    backend = LinuxBackend()
    transport_map = backend._get_transport_map(
        {
            "/dev/sda": {"ID_USB_DRIVER": "usb-storage"},
            "/dev/sdb": {"ID_USB_DRIVER": "uas"},
            "/dev/sdc": {},
        }
    )

    assert transport_map == {
        "/dev/sda": "BOT",
        "/dev/sdb": "UAS",
        "/dev/sdc": "Unknown",
    }


def test_get_controller_map_resolves_controller_name_from_pci_address():
    with patch.object(
        LinuxBackend,
        "_get_pci_controller_name",
        return_value="Intel",
    ):
        backend = LinuxBackend()
        controller_map = backend._get_controller_map(
            {"/dev/sda": {"ID_PATH": "pci-0000:00:14.0-usb-0:1:1.0-scsi-0:0:0:0"}}
        )

    assert controller_map == {"/dev/sda": "Intel"}


def test_get_pci_controller_name_returns_manufacturer_only():
    mock_result = SimpleNamespace(
        returncode=0,
        stdout=(
            "00:14.0 USB controller: "
            "Intel Corporation Alder Lake PCH USB 3.2 xHCI Host Controller (rev 01)\n"
        ),
        stderr="",
    )

    with patch("usb_tool.backend.linux.subprocess.run", return_value=mock_result):
        backend = LinuxBackend()
        controller_name = backend._get_pci_controller_name("0000:00:14.0")

    assert controller_name == "Intel"


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
