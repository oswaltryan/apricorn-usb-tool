# src/usb_tool/models.py

from dataclasses import dataclass
from typing import Any


@dataclass
class UsbDeviceInfo:
    bcdUSB: float
    idVendor: str
    idProduct: str
    bcdDevice: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    driveSizeGB: str
    mediaType: str
    driverTransport: str = "Unknown"
    blockDevice: str | None = None
    # These might be added dynamically or during instantiation
    usbController: str = "N/A"
    usbDriverProvider: str = "N/A"
    usbDriverVersion: str = "N/A"
    usbDriverInf: str = "N/A"
    diskDriverProvider: str = "N/A"
    diskDriverVersion: str = "N/A"
    diskDriverInf: str = "N/A"
    busNumber: int = -1
    deviceAddress: int = -1
    physicalDriveNum: int = -1
    driveLetter: str = "Not Formatted"
    fileSystem: str | None = None
    readOnly: bool = False
    # Version info fields (optional)
    scbPartNumber: str | None = None
    hardwareVersion: str | None = None
    modelID: str | None = None
    mcuFW: str | None = None
    bridgeFW: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = vars(self).copy()
        # We might want to remove None values or specifically bridgeFW here
        return {k: v for k, v in d.items() if v is not None}
