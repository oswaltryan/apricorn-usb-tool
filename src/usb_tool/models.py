# src/usb_tool/models.py

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class UsbDeviceInfo:
    bcdUSB: float
    idVendor: str
    idProduct: str
    bcdDevice: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    SCSIDevice: bool
    driveSizeGB: str
    mediaType: str
    # These might be added dynamically or during instantiation
    usbController: str = "N/A"
    busNumber: int = -1
    deviceAddress: int = -1
    physicalDriveNum: int = -1
    driveLetter: str = "Not Formatted"
    readOnly: bool = False
    # Version info fields (optional)
    scbPartNumber: Optional[str] = None
    hardwareVersion: Optional[str] = None
    modelID: Optional[str] = None
    mcuFW: Optional[str] = None
    bridgeFW: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = vars(self).copy()
        # We might want to remove None values or specifically bridgeFW here
        return {k: v for k, v in d.items() if v is not None}
