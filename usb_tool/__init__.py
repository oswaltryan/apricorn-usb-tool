"""usb_tool package exports."""

from __future__ import annotations

import importlib
import platform
from types import ModuleType
from typing import Any

__all__ = ["find_apricorn_device", "main", "UsbDeviceInfo"]

_PLATFORM_MODULE: ModuleType | None = None


def _load_platform_module() -> ModuleType:
    """Return the platform-specific module, importing it lazily."""
    global _PLATFORM_MODULE
    if _PLATFORM_MODULE is not None:
        return _PLATFORM_MODULE

    system = platform.system().lower()
    if system.startswith("win"):
        module_name = ".windows_usb"
    elif system.startswith("darwin"):
        module_name = ".mac_usb"
    else:
        module_name = ".linux_usb"

    _PLATFORM_MODULE = importlib.import_module(module_name, __name__)
    return _PLATFORM_MODULE


def __getattr__(name: str) -> Any:
    if name in __all__:
        return getattr(_load_platform_module(), name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
