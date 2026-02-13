# src/usb_tool/services.py

import platform
from typing import List, Optional, Any
from .backend.base import AbstractBackend
from .models import UsbDeviceInfo
from .device_version import query_device_version


def populate_device_version(
    vendor_id: int,
    product_id: int,
    serial_number: str,
    bsd_name: Optional[str] = None,
    physical_drive_num: Optional[int] = None,
) -> dict:
    """
    Queries the device version and returns a dictionary of formatted strings.
    """
    version_info = {
        "scbPartNumber": "N/A",
        "hardwareVersion": "N/A",
        "modelID": "N/A",
        "mcuFW": "N/A",
        "bridgeFW": "N/A",
    }

    try:
        _ver = query_device_version(
            vendor_id,
            product_id,
            serial_number,
            bsd_name=bsd_name,
            physical_drive_num=physical_drive_num,
        )

        if getattr(_ver, "scb_part_number", "N/A") != "N/A":
            version_info["scbPartNumber"] = _ver.scb_part_number

        version_info["hardwareVersion"] = (
            getattr(_ver, "hardware_version", "N/A") or "N/A"
        )

        version_info["modelID"] = getattr(_ver, "model_id", "N/A") or "N/A"

        mj, mn, sb = getattr(_ver, "mcu_fw", (None, None, None))
        if mj is not None and mn is not None and sb is not None:
            version_info["mcuFW"] = f"{mj}.{mn}.{sb}"

        version_info["bridgeFW"] = getattr(_ver, "bridge_fw", "N/A") or "N/A"

    except Exception:
        pass

    return version_info


class DeviceManager:
    def __init__(self, backend: Optional[AbstractBackend] = None):
        if backend is None:
            self.backend = self._get_default_backend()
        else:
            self.backend = backend

    def _get_default_backend(self) -> AbstractBackend:
        system = platform.system().lower()
        if system.startswith("win"):
            from .backend.windows import WindowsBackend

            return WindowsBackend()
        elif system.startswith("linux"):
            from .backend.linux import LinuxBackend

            return LinuxBackend()
        elif system.startswith("darwin"):
            from .backend.macos import MacOSBackend

            return MacOSBackend()
        else:
            raise NotImplementedError(f"Unsupported platform: {system}")

    def list_devices(self, minimal: bool = False) -> List[UsbDeviceInfo]:
        devices = self.backend.scan_devices(minimal=minimal)
        return self.backend.sort_devices(devices)

    def poke(self, device_identifier: Any) -> bool:
        return self.backend.poke_device(device_identifier)
