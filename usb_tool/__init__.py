# usb_tool/__init__.py

import platform

if platform.system().lower().startswith("win"):
    from usb_tool.windows_usb import (
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
    from usb_tool.mac_usb import (
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
    from usb_tool.linux_usb import find_apricorn_device, main, UsbDeviceInfo

    __all__ = [
        "find_apricorn_device",
        "main",
        "UsbDeviceInfo",
    ]
