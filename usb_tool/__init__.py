# usb_tool/__init__.py

import platform

if platform.system().lower().startswith("win"):
    from .windows_usb import (
        list_usb_drives,
        find_apricorn_device,
        main,
        WinUsbDeviceInfo,
        get_usb_devices_from_wmi
    )
    __all__ = [
        "list_usb_drives",
        "find_apricorn_device",
        "main",
        "WinUsbDeviceInfo",
        "get_usb_devices_from_wmi",
    ]
else:
    from .linux_usb import (
        list_usb_drives,
        find_apricorn_device,
        main,
        WinUsbDeviceInfo
    )
    __all__ = [
        "list_usb_drives",
        "find_apricorn_device",
        "main",
        "WinUsbDeviceInfo",
    ]
