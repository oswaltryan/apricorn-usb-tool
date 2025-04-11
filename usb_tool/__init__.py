# usb_tool/__init__.py

import platform

if platform.system().lower().startswith("win"):
    from .windows_usb import (
        find_apricorn_device,
        main,
        WinUsbDeviceInfo,
    )
    __all__ = [
        "list_usb_drives",
        "find_apricorn_device",
        "main",
        "WinUsbDeviceInfo",
    ]
else:
    from .linux_usb import (
        list_usb_drives,
        find_apricorn_device,
        main,
        LinuxUsbDeviceInfo
    )
    __all__ = [
        "list_usb_drives",
        "find_apricorn_device",
        "main",
        "LinuxUsbDeviceInfo",
    ]
