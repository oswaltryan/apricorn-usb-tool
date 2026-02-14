# src/usb_tool/__init__.py
from .backend import windows as windows_usb
from .backend import linux as linux_usb
from .backend import macos as mac_usb
from .services import DeviceManager


def find_apricorn_device(minimal: bool = False):
    manager = DeviceManager()
    return manager.list_devices(minimal=minimal)


__all__ = ["windows_usb", "linux_usb", "mac_usb", "find_apricorn_device"]
