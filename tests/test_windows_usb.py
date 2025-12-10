"""Unit tests for windows_usb module.

Stubs are used to stand in for Windows-specific dependencies so the tests
can run on any platform.
"""

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Provide light‑weight stand‑ins for Windows-only dependencies before import.
# ---------------------------------------------------------------------------
libusb_stub = types.ModuleType("libusb")
libusb_stub.config = lambda **kwargs: None  # type: ignore
libusb_stub.get_string_descriptor_ascii = lambda *a, **k: 0  # type: ignore
sys.modules["libusb"] = libusb_stub

win32com_stub = types.ModuleType("win32com")
client_stub = types.ModuleType("win32com.client")


class _DummyService:
    def ExecQuery(self, query):
        return []


class _DummyLocator:
    def ConnectServer(self, *args, **kwargs):
        return _DummyService()


client_stub.Dispatch = lambda name: _DummyLocator()  # type: ignore
win32com_stub.client = client_stub  # type: ignore
sys.modules["win32com"] = win32com_stub
sys.modules["win32com.client"] = client_stub

import usb_tool.windows_usb as windows_usb  # noqa: E402


# ---------------------------
# Utility Function Tests
# ---------------------------


def test_bytes_to_gb_converts_bytes_to_gigabytes():
    """Simple sanity check for byte conversion."""
    assert windows_usb.bytes_to_gb(1024**3) == 1.0


def test_find_closest_returns_expected_value():
    """find_closest should pick the nearest option."""
    assert windows_usb.find_closest(6, [1, 7, 10]) == 7


def test_parse_usb_version_decodes_bcd_numbers():
    """parse_usb_version converts BCD to human readable string."""
    assert windows_usb.parse_usb_version(0x0310) == "3.1"
    assert windows_usb.parse_usb_version(0x0211) == "2.11"


# ---------------------------
# PowerShell helper tests
# ---------------------------


def test_get_drive_letter_via_ps_handles_invalid_index():
    """A negative drive index should yield 'N/A'."""
    assert windows_usb.get_drive_letter_via_ps(-1) == "Not Formatted"


def test_get_drive_letter_via_ps_parses_output():
    """Valid PowerShell output is returned as-is."""
    mock_result = SimpleNamespace(stdout="E:\n", returncode=0)
    with patch("usb_tool.windows_usb.subprocess.run", return_value=mock_result):
        assert windows_usb.get_drive_letter_via_ps(1) == "E:"


def test_get_wmi_usb_devices_skips_excluded_pids():
    """PNP entries with excluded PIDs must be ignored."""

    class DummyDevice:
        def __init__(self, device_id, description="USB Mass Storage Device"):
            self.DeviceID = device_id
            self.Description = description

    devices = [
        DummyDevice(r"USB\\VID_0984&PID_0221&REV_0000\\SER_BAD1"),
        DummyDevice(r"USB\\VID_0984&PID_0301\\SER_BAD2"),
        DummyDevice(r"USB\\VID_0984&PID_1234&REV_0000\\SER_GOOD"),
    ]

    class DummyService:
        def ExecQuery(self, query):
            return devices

    with patch("usb_tool.windows_usb.service", DummyService()):
        result = windows_usb.get_wmi_usb_devices()

    assert len(result) == 1
    assert result[0]["pid"] == "1234"
    assert result[0]["serial"] == "SER_GOOD"


def test_should_retry_scan_detects_partial_lists():
    """Retry logic should trigger when lengths are mismatched and non-zero."""
    assert windows_usb._should_retry_scan([0, 1, 1, 0]) is True
    assert windows_usb._should_retry_scan([0, 0, 0, 0]) is False
    assert windows_usb._should_retry_scan([2, 2, 2, 2]) is False


def test_find_apricorn_device_retries_once_on_partial_scan():
    """A partial first pass should trigger a single retry before giving up."""
    fake_device = SimpleNamespace()
    scan_results = [
        (None, [0, 1, 1, 0]),  # First pass: partial data, no devices
        ([fake_device], [1, 1, 1, 1]),  # Second pass: complete
    ]

    with (
        patch(
            "usb_tool.windows_usb._perform_scan_pass", side_effect=scan_results
        ) as scan_mock,
        patch("usb_tool.windows_usb.time.sleep") as sleep_mock,
    ):
        devices = windows_usb.find_apricorn_device()

    assert devices == [fake_device]
    assert scan_mock.call_count == 2
    sleep_mock.assert_called_once()
