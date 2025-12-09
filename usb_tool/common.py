from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING
import sys


@dataclass
class UsbDeviceInfo:
    """
    Dataclass representing a USB device information structure.
    Includes fields for Windows, Linux, and macOS.
    """

    # Common fields
    bcdUSB: float
    idVendor: str
    idProduct: str
    bcdDevice: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    SCSIDevice: bool = False
    driveSizeGB: Any = 0
    mediaType: str = "Unknown"

    if sys.platform == "win32":
        # Windows-specific fields
        usbController: Optional[str] = ""
        busNumber: Optional[int] = 0
        deviceAddress: Optional[int] = 0
        physicalDriveNum: Optional[int] = 0
        driveLetter: Optional[str] = "Not Formatted"
        readOnly: Optional[bool] = False

    scbPartNumber: str = "N/A"
    hardwareVersion: str = "N/A"
    modelID: str = "N/A"
    mcuFW: str = "N/A"
    bridgeFW: str = "N/A"


_device_version_imported = False
if TYPE_CHECKING:
    from usb_tool.device_version import query_device_version

try:
    from usb_tool.device_version import query_device_version

    _device_version_imported = True
except (ImportError, ModuleNotFoundError):
    pass


def populate_device_version(
    vendor_id: int, product_id: int, serial_number: str, bsd_name: Optional[str] = None
) -> dict:
    """
    Queries the device version and returns a dictionary of formatted strings.

    Args:
        vendor_id: The vendor ID of the USB device.
        product_id: The product ID of the USB device.
        serial_number: The serial number of the USB device.

    Returns:
        A dictionary with version information.
    """
    version_info = {
        "scbPartNumber": "N/A",
        "hardwareVersion": "N/A",
        "modelID": "N/A",
        "mcuFW": "N/A",
        "bridgeFW": "N/A",
    }

    if not _device_version_imported:
        return version_info

    try:
        _ver = query_device_version(vendor_id, product_id, serial_number, bsd_name=bsd_name)

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
        # Silently fail, returning the default "N/A" values
        pass

    return version_info
