# src/usb_tool/backend/base.py

from abc import ABC, abstractmethod
from typing import Any


class AbstractBackend(ABC):
    @abstractmethod
    def scan_devices(
        self,
        expanded: bool = False,
        profile_scan: bool = False,
    ) -> list[Any]:
        """Scan for Apricorn devices on the current platform."""
        pass

    @abstractmethod
    def poke_device(self, device_identifier: Any) -> bool:
        """Send a SCSI READ(10) command to the specified device."""
        pass

    @abstractmethod
    def sort_devices(self, devices: list[Any]) -> list[Any]:
        """Sort devices in a platform-appropriate order."""
        pass
