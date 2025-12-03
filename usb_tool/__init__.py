# usb_tool/__init__.py

import platform

if platform.system().lower().startswith("win"):
    from .windows_usb import (
        find_apricorn_device,
        main,
        UsbDeviceInfo,
    )

    __all__ = [
        "find_apricorn_device",
        "main",
        "UsbDeviceInfo",
    ]
elif platform.system().lower().startswith("darwin"):
    from .mac_usb import (
        find_apricorn_device,
        main,
        UsbDeviceInfo,
    )

    __all__ = [
        "find_apricorn_device",
        "main",
        "UsbDeviceInfo",
    ]
else:
    from .linux_usb import find_apricorn_device, main, UsbDeviceInfo

    __all__ = [
        "find_apricorn_device",
        "main",
        "UsbDeviceInfo",
    ]
