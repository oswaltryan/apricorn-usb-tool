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
libusb_stub.config = lambda **kwargs: None
libusb_stub.get_string_descriptor_ascii = lambda *a, **k: 0
sys.modules["libusb"] = libusb_stub

win32com_stub = types.ModuleType("win32com")
client_stub = types.ModuleType("win32com.client")


class _DummyService:
    def ExecQuery(self, query):
        return []


class _DummyLocator:
    def ConnectServer(self, *args, **kwargs):
        return _DummyService()


client_stub.Dispatch = lambda name: _DummyLocator()
win32com_stub.client = client_stub
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
    assert windows_usb.get_drive_letter_via_ps(-1) == "N/A"


def test_get_drive_letter_via_ps_parses_output():
    """Valid PowerShell output is returned as-is."""
    mock_result = SimpleNamespace(stdout="E:\n", returncode=0)
    with patch("usb_tool.windows_usb.subprocess.run", return_value=mock_result):
        assert windows_usb.get_drive_letter_via_ps(1) == "E:"
