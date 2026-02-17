# src/usb_tool/__init__.py
from importlib import import_module
from typing import Any

from .services import DeviceManager


def find_apricorn_device(minimal: bool = False):
    manager = DeviceManager()
    return manager.list_devices(minimal=minimal)


def __getattr__(name: str) -> Any:
    if name == "windows_usb":
        return import_module(".backend.windows", __name__)
    if name == "linux_usb":
        return import_module(".backend.linux", __name__)
    if name == "mac_usb":
        return import_module(".backend.macos", __name__)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["windows_usb", "linux_usb", "mac_usb", "find_apricorn_device"]
