"""Unit tests for windows_usb module."""

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

# We need to ensure we can import WindowsBackend even on non-Windows
# But since we are on Windows (based on user context), win32com exists.
# The error "cannot import name 'util'" suggests a broken win32com installation or conflict.
# Assuming we want to run this test safely:

from usb_tool.backend.windows import WindowsBackend


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
    wmi_usb_devices = [
        {"pid": "1407", "vid": "0984", "serial": "SER123", "manufacturer": "Apricorn"}
    ]
    wmi_usb_drives = [
        {"size_gb": 15.8, "iProduct": "Secure Key 3.0", "mediaType": "Basic Disk"}
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


def test_instantiate_devices_falls_back_to_powershell_for_drive_letter():
    backend = object.__new__(WindowsBackend)
    wmi_usb_devices = [
        {"pid": "1407", "vid": "0984", "serial": "SER123", "manufacturer": "Apricorn"}
    ]
    wmi_usb_drives = [
        {"size_gb": 15.8, "iProduct": "Secure Key 3.0", "mediaType": "Basic Disk"}
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
    wmi_usb_devices = [
        {"pid": "1407", "vid": "0984", "serial": "SER123", "manufacturer": "Apricorn"}
    ]
    wmi_usb_drives = [
        {"size_gb": 15.8, "iProduct": "Secure Key 3.0", "mediaType": "Basic Disk"}
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
