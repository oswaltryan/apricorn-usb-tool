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
