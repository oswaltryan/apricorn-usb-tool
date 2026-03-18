"""Unit tests for windows_usb module."""

import sys
import pytest

# Skip this entire module if not on Windows
if sys.platform != "win32":
    pytest.skip("Windows only tests", allow_module_level=True)

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from usb_tool.backend.windows import (
    WindowsBackend,
    _normalize_logical_disk_identifier,
)


def test_get_drive_letter_via_ps_handles_invalid_index():
    with patch("usb_tool.backend.windows.win32com.client.Dispatch"):
        backend = WindowsBackend()
        assert backend.get_drive_letter_via_ps(-1) == "Not Formatted"


def test_get_drive_letter_via_ps_parses_output():
    mock_result = SimpleNamespace(stdout="E:\n", returncode=0)
    with (
        patch("usb_tool.backend.windows.win32com.client.Dispatch"),
        patch("usb_tool.backend.windows.subprocess.run", return_value=mock_result),
    ):
        backend = WindowsBackend()
        assert backend.get_drive_letter_via_ps(1) == "E:"


def test_get_wmi_usb_devices_skips_excluded_pids():
    class DummyDevice:
        def __init__(self, device_id, description="USB Mass Storage Device"):
            self.DeviceID = device_id
            self.Description = description

    devices = [
        DummyDevice(r"USB\\VID_0984&PID_0221&REV_0000\\SER_BAD1"),
        DummyDevice(r"USB\\VID_0984&PID_0301\\SER_BAD2"),
        DummyDevice(r"USB\\VID_0984&PID_1234&REV_0000\\SER_GOOD"),
    ]

    mock_service = MagicMock()
    mock_service.ExecQuery.return_value = devices

    with patch("usb_tool.backend.windows.win32com.client.Dispatch") as mock_dispatch:
        mock_dispatch.return_value.ConnectServer.return_value = mock_service

        backend = WindowsBackend()
        # Ensure our mock service is used (it should be via __init__)
        # backend.service is set in __init__

        result = backend._get_wmi_usb_devices()

    assert len(result) == 1
    assert result[0]["pid"] == "1234"
    assert result[0]["serial"] == "SER_GOOD"


def test_should_retry_scan_detects_partial_lists():
    with patch("usb_tool.backend.windows.win32com.client.Dispatch"):
        backend = WindowsBackend()
        assert backend._should_retry_scan([0, 1, 1, 0]) is True
        assert backend._should_retry_scan([0, 0, 0, 0]) is False
        assert backend._should_retry_scan([2, 2, 2, 2]) is False


def test_find_apricorn_device_retries_once_on_partial_scan():
    fake_device = SimpleNamespace()
    scan_results = [
        (None, [0, 1, 1, 0]),
        ([fake_device], [1, 1, 1, 1]),
    ]

    with (
        patch("usb_tool.backend.windows.win32com.client.Dispatch"),
        patch.object(
            WindowsBackend, "_perform_scan_pass", side_effect=scan_results
        ) as scan_mock,
        patch("time.sleep"),
    ):
        backend = WindowsBackend()
        devices = backend.scan_devices()

    assert devices == [fake_device]
    assert scan_mock.call_count == 2


def test_instantiate_devices_sets_drive_letter_from_map():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    wmi_usb_devices = [
        {
            "pid": "1407",
            "vid": "0984",
            "serial": "SER123",
            "manufacturer": "Apricorn",
            "usbDriverProvider": "Apricorn",
            "usbDriverVersion": "1.2.3.4",
            "usbDriverInf": "oem17.inf",
        }
    ]
    wmi_usb_drives = [
        {
            "size_gb": 15.8,
            "iProduct": "Secure Key 3.0",
            "mediaType": "Basic Disk",
            "pnpdeviceid": r"USBSTOR\\DISK&VEN_APRICORN&PROD_KEY\\SER123&0",
            "diskDriverInfo": {
                "provider": "Microsoft",
                "version": "10.0.1",
                "inf": "disk.inf",
            },
        }
    ]
    usb_controllers = [{"ControllerName": "Intel"}]
    libusb_data = [
        {"bcdUSB": 3.2, "bcdDevice": "0502", "bus_number": 1, "dev_address": 16}
    ]
    physical_drives = {"SER123": 3}
    readonly_map = {3: False}
    drive_letters_map = {3: "F:"}

    with patch("usb_tool.backend.windows.populate_device_version", return_value={}):
        devices = backend._instantiate_devices(
            wmi_usb_devices,
            wmi_usb_drives,
            usb_controllers,
            libusb_data,
            physical_drives,
            readonly_map,
            drive_letters_map,
            include_controller=True,
            include_drive_letter=True,
        )

    assert devices and devices[0].to_dict()["driveLetter"] == "F:"
    serialized = devices[0].to_dict()
    assert serialized["driverTransport"] == "BOT"
    assert serialized["usbDriverProvider"] == "Apricorn"
    assert serialized["diskDriverProvider"] == "Microsoft"


def test_instantiate_devices_falls_back_to_powershell_for_drive_letter():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    wmi_usb_devices = [
        {
            "pid": "1407",
            "vid": "0984",
            "serial": "SER123",
            "manufacturer": "Apricorn",
            "usbDriverProvider": "Apricorn",
            "usbDriverVersion": "1.2.3.4",
            "usbDriverInf": "oem17.inf",
        }
    ]
    wmi_usb_drives = [
        {
            "size_gb": 15.8,
            "iProduct": "Secure Key 3.0",
            "mediaType": "Basic Disk",
            "pnpdeviceid": r"USBSTOR\\DISK&VEN_APRICORN&PROD_KEY\\SER123&0",
            "diskDriverInfo": {
                "provider": "Microsoft",
                "version": "10.0.1",
                "inf": "disk.inf",
            },
        }
    ]
    usb_controllers = [{"ControllerName": "Intel"}]
    libusb_data = [
        {"bcdUSB": 3.2, "bcdDevice": "0502", "bus_number": 1, "dev_address": 16}
    ]
    physical_drives = {"SER123": 3}
    readonly_map = {3: False}
    drive_letters_map = {}

    with (
        patch("usb_tool.backend.windows.populate_device_version", return_value={}),
        patch.object(WindowsBackend, "get_drive_letter_via_ps", return_value="G:"),
    ):
        devices = backend._instantiate_devices(
            wmi_usb_devices,
            wmi_usb_drives,
            usb_controllers,
            libusb_data,
            physical_drives,
            readonly_map,
            drive_letters_map,
            include_controller=True,
            include_drive_letter=True,
        )

    assert devices and devices[0].to_dict()["driveLetter"] == "G:"


def test_instantiate_devices_omits_drive_letter_in_minimal_mode():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    wmi_usb_devices = [
        {
            "pid": "1407",
            "vid": "0984",
            "serial": "SER123",
            "manufacturer": "Apricorn",
            "usbDriverProvider": "Apricorn",
            "usbDriverVersion": "1.2.3.4",
            "usbDriverInf": "oem17.inf",
        }
    ]
    wmi_usb_drives = [
        {
            "size_gb": 15.8,
            "iProduct": "Secure Key 3.0",
            "mediaType": "Basic Disk",
            "pnpdeviceid": r"SCSI\\DISK&VEN_APRICORN&PROD_KEY\\MSFT30SER123&0",
            "diskDriverInfo": {
                "provider": "Microsoft",
                "version": "10.0.1",
                "inf": "disk.inf",
            },
        }
    ]
    usb_controllers = [{"ControllerName": "Intel"}]
    libusb_data = [
        {"bcdUSB": 3.2, "bcdDevice": "0502", "bus_number": 1, "dev_address": 16}
    ]
    physical_drives = {"SER123": 3}
    readonly_map = {3: False}
    drive_letters_map = {3: "F:"}

    with patch("usb_tool.backend.windows.populate_device_version", return_value={}):
        devices = backend._instantiate_devices(
            wmi_usb_devices,
            wmi_usb_drives,
            usb_controllers,
            libusb_data,
            physical_drives,
            readonly_map,
            drive_letters_map,
            include_controller=False,
            include_drive_letter=False,
        )

    assert devices
    serialized = devices[0].to_dict()
    assert "driveLetter" not in serialized
    assert "usbController" not in serialized
    assert serialized["driverTransport"] == "UAS"


def test_get_signed_driver_info_returns_default_on_query_failure():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    backend.service = MagicMock()
    backend.service.ExecQuery.side_effect = RuntimeError("boom")

    result = backend._get_signed_driver_info(r"USB\\VID_0984&PID_1407\\SER123")

    assert result == {"provider": "N/A", "version": "N/A", "inf": "N/A"}


def test_get_signed_driver_info_map_builds_bulk_lookup():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1

    class DummyDriverRecord:
        DeviceID = r"USB\\VID_0984&PID_1407&REV_0300\\SER123"
        DriverProviderName = "Apricorn"
        DriverVersion = "21.46.5.13"
        InfName = "oem17.inf"

    backend.service = MagicMock()
    backend.service.ExecQuery.return_value = [DummyDriverRecord()]

    result = backend._get_signed_driver_info_map({DummyDriverRecord.DeviceID})

    assert result[DummyDriverRecord.DeviceID]["provider"] == "Apricorn"
    assert result[DummyDriverRecord.DeviceID]["version"] == "21.46.5.13"
    assert result[DummyDriverRecord.DeviceID]["inf"] == "oem17.inf"


def test_apply_usb_driver_info_populates_usb_driver_fields():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    devices = [
        {
            "device_id": r"USB\\VID_0984&PID_1407&REV_0300\\SER123",
            "usbDriverProvider": "N/A",
            "usbDriverVersion": "N/A",
            "usbDriverInf": "N/A",
        }
    ]

    backend._apply_usb_driver_info(
        devices,
        {
            r"USB\\VID_0984&PID_1407&REV_0300\\SER123": {
                "provider": "Apricorn",
                "version": "21.46.5.13",
                "inf": "oem17.inf",
            }
        },
    )

    assert devices[0]["usbDriverProvider"] == "Apricorn"
    assert devices[0]["usbDriverVersion"] == "21.46.5.13"
    assert devices[0]["usbDriverInf"] == "oem17.inf"


def test_perform_scan_pass_batches_usb_driver_lookup_only_for_default_mode():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    backend._get_wmi_usb_devices = MagicMock(
        return_value=[
            {
                "vid": "0984",
                "pid": "1407",
                "serial": "SER123",
                "device_id": r"USB\\VID_0984&PID_1407\\SER123",
                "description": "Apricorn USB",
                "usbDriverProvider": "N/A",
                "usbDriverVersion": "N/A",
                "usbDriverInf": "N/A",
            }
        ]
    )
    backend._get_wmi_diskdrives = MagicMock(return_value=[])
    backend._get_wmi_usb_drives = MagicMock(
        return_value=[
            {
                "size_gb": 15.8,
                "iProduct": "Secure Key 3.0",
                "mediaType": "Basic Disk",
                "pnpdeviceid": r"USBSTOR\\DISK&VEN_APRICORN&PROD_KEY\\SER123&0",
                "diskDriverInfo": {
                    "provider": "N/A",
                    "version": "N/A",
                    "inf": "N/A",
                },
            }
        ]
    )
    backend._get_apricorn_libusb_data = MagicMock(
        return_value=[
            {"bcdUSB": 3.2, "bcdDevice": "0502", "bus_number": 1, "dev_address": 2}
        ]
    )
    backend._get_physical_drive_number = MagicMock(return_value={})
    backend._sort_wmi_drives = MagicMock(side_effect=lambda devices, drives: drives)
    backend._sort_libusb_data = MagicMock(side_effect=lambda devices, data: data)
    backend._get_usb_readonly_status_map_wmi = MagicMock(return_value={})
    backend._get_drive_letters_map_wmi = MagicMock(return_value={})
    backend._apply_usb_driver_info = MagicMock()
    backend._apply_disk_driver_info = MagicMock()
    backend._instantiate_devices = MagicMock(return_value=[])
    backend._get_signed_driver_info_map = MagicMock(return_value={})

    backend._perform_scan_pass(minimal=False, expanded=False)

    backend._get_signed_driver_info_map.assert_not_called()
    backend._apply_usb_driver_info.assert_not_called()
    backend._apply_disk_driver_info.assert_not_called()


def test_perform_scan_pass_includes_disk_driver_lookup_for_json_mode():
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = False
    backend._scan_pass_index = 1
    backend._get_wmi_usb_devices = MagicMock(
        return_value=[
            {
                "vid": "0984",
                "pid": "1407",
                "serial": "SER123",
                "device_id": r"USB\\VID_0984&PID_1407\\SER123",
                "description": "Apricorn USB",
                "usbDriverProvider": "N/A",
                "usbDriverVersion": "N/A",
                "usbDriverInf": "N/A",
            }
        ]
    )
    backend._get_wmi_diskdrives = MagicMock(return_value=[])
    backend._get_wmi_usb_drives = MagicMock(
        return_value=[
            {
                "size_gb": 15.8,
                "iProduct": "Secure Key 3.0",
                "mediaType": "Basic Disk",
                "pnpdeviceid": r"USBSTOR\\DISK&VEN_APRICORN&PROD_KEY\\SER123&0",
                "diskDriverInfo": {
                    "provider": "N/A",
                    "version": "N/A",
                    "inf": "N/A",
                },
            }
        ]
    )
    backend._get_apricorn_libusb_data = MagicMock(
        return_value=[
            {"bcdUSB": 3.2, "bcdDevice": "0502", "bus_number": 1, "dev_address": 2}
        ]
    )
    backend._get_physical_drive_number = MagicMock(return_value={})
    backend._sort_wmi_drives = MagicMock(side_effect=lambda devices, drives: drives)
    backend._sort_libusb_data = MagicMock(side_effect=lambda devices, data: data)
    backend._get_usb_readonly_status_map_wmi = MagicMock(return_value={})
    backend._get_drive_letters_map_wmi = MagicMock(return_value={})
    backend._apply_usb_driver_info = MagicMock()
    backend._apply_disk_driver_info = MagicMock()
    backend._instantiate_devices = MagicMock(return_value=[])
    backend._get_signed_driver_info_map = MagicMock(return_value={})

    backend._perform_scan_pass(minimal=False, expanded=True)

    backend._get_signed_driver_info_map.assert_called_once_with(
        {
            r"USB\\VID_0984&PID_1407\\SER123",
            r"USBSTOR\\DISK&VEN_APRICORN&PROD_KEY\\SER123&0",
        }
    )
    backend._apply_disk_driver_info.assert_called_once()


def test_perform_scan_pass_emits_profile_output_when_enabled(monkeypatch, capsys):
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = True
    backend._scan_pass_index = 1
    backend._get_wmi_usb_devices = MagicMock(return_value=[])
    backend._get_wmi_diskdrives = MagicMock(return_value=[])
    backend._get_wmi_usb_drives = MagicMock(return_value=[])
    backend._get_apricorn_libusb_data = MagicMock(return_value=[])
    backend._get_physical_drive_number = MagicMock(return_value={})
    backend._get_signed_driver_info_map = MagicMock(return_value={})
    backend._apply_usb_driver_info = MagicMock()
    backend._apply_disk_driver_info = MagicMock()
    backend._sort_wmi_drives = MagicMock(side_effect=lambda devices, drives: drives)
    backend._get_usb_controllers_wmi = MagicMock(return_value=[])
    backend._sort_usb_controllers = MagicMock(
        side_effect=lambda devices, controllers: controllers
    )
    backend._sort_libusb_data = MagicMock(side_effect=lambda devices, data: data)
    backend._get_usb_readonly_status_map_wmi = MagicMock(return_value={})
    backend._get_drive_letters_map_wmi = MagicMock(return_value={})
    backend._instantiate_devices = MagicMock(return_value=[])

    backend._perform_scan_pass(minimal=False, expanded=False)

    captured = capsys.readouterr()
    assert "windows-scan-profile" in captured.err
    assert "pass=1" in captured.err
    assert "wmi_usb_devices=" in captured.err
    assert "instantiate_devices=" in captured.err


def test_get_drive_letters_map_wmi_emits_partition_diagnostics(capsys):
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = True
    backend._scan_pass_index = 1
    backend.service = MagicMock()

    class DummyDisk:
        Index = 3
        DeviceID = r"\\.\PHYSICALDRIVE3"

    class DummyAssoc:
        def __init__(self, antecedent, dependent):
            self.Antecedent = antecedent
            self.Dependent = dependent

    backend.service.ExecQuery.side_effect = [
        [
            DummyAssoc(
                'Win32_DiskDrive.DeviceID="\\\\\\\\.\\\\PHYSICALDRIVE3"',
                "Disk #3, Partition #0",
            )
        ],
        [DummyAssoc("Disk #3, Partition #0", "D:")],
    ]
    result = backend._get_drive_letters_map_wmi([DummyDisk()], {3})

    captured = capsys.readouterr()
    assert result == {3: "D:"}
    assert (
        "windows-drive-letter-profile: pass=1 disk_index=3 stage=bulk_partitions count=1"
        in captured.err
    )
    assert (
        "windows-drive-letter-profile: pass=1 disk_index=3 stage=bulk_partition_result partition=Disk #3, Partition #0 letters=D:"
        in captured.err
    )


def test_instantiate_devices_emits_fallback_diagnostics(capsys):
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = True
    backend._scan_pass_index = 1
    wmi_usb_devices = [
        {
            "pid": "1407",
            "vid": "0984",
            "serial": "SER123",
            "manufacturer": "Apricorn",
            "usbDriverProvider": "N/A",
            "usbDriverVersion": "N/A",
            "usbDriverInf": "N/A",
        }
    ]
    wmi_usb_drives = [
        {
            "size_gb": 15.8,
            "iProduct": "Secure Key 3.0",
            "mediaType": "Basic Disk",
            "pnpdeviceid": r"USBSTOR\\DISK&VEN_APRICORN&PROD_KEY\\SER123&0",
            "diskDriverInfo": {
                "provider": "N/A",
                "version": "N/A",
                "inf": "N/A",
            },
        }
    ]
    usb_controllers = [{"ControllerName": "Intel"}]
    libusb_data = [
        {"bcdUSB": 3.2, "bcdDevice": "0502", "bus_number": 1, "dev_address": 16}
    ]
    with (
        patch("usb_tool.backend.windows.populate_device_version", return_value={}),
        patch.object(WindowsBackend, "get_drive_letter_via_ps", return_value="D:"),
    ):
        devices = backend._instantiate_devices(
            wmi_usb_devices,
            wmi_usb_drives,
            usb_controllers,
            libusb_data,
            {"SER123": 3},
            {3: False},
            {},
            include_controller=True,
            include_drive_letter=True,
        )

    captured = capsys.readouterr()
    assert devices[0].driveLetter == "D:"
    assert (
        "windows-drive-letter-profile: pass=1 disk_index=3 stage=fallback_triggered serial=SER123 size_raw=15.8"
        in captured.err
    )
    assert (
        "windows-drive-letter-profile: pass=1 disk_index=3 stage=fallback_result letter=D:"
        in captured.err
    )


def test_get_drive_letters_map_wmi_uses_bulk_associations_for_drive_letter(capsys):
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = True
    backend._scan_pass_index = 1
    backend.service = MagicMock()

    class DummyDisk:
        Index = 1
        DeviceID = r"\\.\PHYSICALDRIVE1"

    class DummyAssoc:
        def __init__(self, antecedent, dependent):
            self.Antecedent = antecedent
            self.Dependent = dependent

    backend.service.ExecQuery.side_effect = [
        [
            DummyAssoc(
                'Win32_DiskDrive.DeviceID="\\\\\\\\.\\\\PHYSICALDRIVE1"',
                '\\\\DESKTOP-NF3343M\\root\\cimv2:Win32_DiskPartition.DeviceID="Disk #1, Partition #0"',
            )
        ],
        [
            DummyAssoc(
                '\\\\DESKTOP-NF3343M\\root\\cimv2:Win32_DiskPartition.DeviceID="Disk #1, Partition #0"',
                '\\\\DESKTOP-NF3343M\\root\\cimv2:Win32_LogicalDisk.DeviceID="D:"',
            )
        ],
    ]
    result = backend._get_drive_letters_map_wmi([DummyDisk()], {1})

    captured = capsys.readouterr()
    assert result == {1: "D:"}
    assert (
        "windows-drive-letter-profile: pass=1 disk_index=1 stage=bulk_partitions count=1"
        in captured.err
    )
    assert (
        "windows-drive-letter-profile: pass=1 disk_index=1 stage=bulk_partition_result "
        'partition=\\\\DESKTOP-NF3343M\\root\\cimv2:Win32_DiskPartition.DeviceID="Disk #1, Partition #0" '
        "letters=D:" in captured.err
    )


def test_normalize_logical_disk_identifier_extracts_drive_letter():
    assert (
        _normalize_logical_disk_identifier(
            '\\\\DESKTOP-NF3343M\\root\\cimv2:Win32_LogicalDisk.DeviceID="D:"'
        )
        == "D:"
    )


def test_get_drive_letters_map_wmi_skips_logging_when_no_candidate_indices(capsys):
    backend = object.__new__(WindowsBackend)
    backend._profile_scan_enabled = True
    backend._scan_pass_index = 2
    backend.service = MagicMock()

    class DummyDisk:
        Index = 0
        DeviceID = r"\\.\PHYSICALDRIVE0"

    result = backend._get_drive_letters_map_wmi([DummyDisk()], set())

    captured = capsys.readouterr()
    assert result == {}
    assert (
        "windows-drive-letter-profile: pass=2 skipped=no_candidate_drive_indices"
        in captured.err
    )
