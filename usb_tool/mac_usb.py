#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional
import json
from pprint import pprint

from .device_config import closest_values
from .utils import bytes_to_gb, find_closest

# Version query (READ BUFFER 0x3C). On macOS, end-to-end permissions
# and disk path resolution may limit availability; fields default to N/A.
try:
    from .device_version import query_device_version
except Exception:
    query_device_version = None  # type: ignore


# -----------------------------
# Same Dataclass as on Windows
# -----------------------------
@dataclass
class macOSUsbDeviceInfo:
    """
    Represents information about an Apricorn USB device on macOS.

    Attributes:
        bcdUSB (float): USB specification release number.
        idVendor (str): Vendor ID assigned by the USB Implementers Forum.
        idProduct (str): Product ID assigned by the manufacturer.
        bcdDevice (str): Device revision number.
        iManufacturer (str): Index of the manufacturer string descriptor.
        iProduct (str): Index of the product string descriptor.
        iSerial (str): Index of the serial number string descriptor.
        SCSIDevice (bool): Indicates if the device uses SCSI commands over USB (UAS).
        driveSizeGB (int): Approximate drive size in Gigabytes.
    """

    bcdUSB: float
    idVendor: str
    idProduct: str
    bcdDevice: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    SCSIDevice: bool = False
    driveSizeGB: int = 0
    # usbController: str = ""
    # blockDevice: str = ""
    mediaType: str = "Unknown"
    # Device version details (best-effort; typically not available without raw disk access)
    scbPartNumber: str = "N/A"
    hardwareVersion: str = "N/A"
    modelID: str = "N/A"
    mcuFW: str = "N/A"
    bridgeFW: str = "N/A"


def sort_devices(devices: list) -> list:
    """Return devices sorted by serial number.

    Args:
        devices: List of ``macOSUsbDeviceInfo`` instances.

    Returns:
        Devices ordered by their ``iSerial`` attribute. Devices lacking a
        serial number are placed at the end.
    """
    if not devices:
        return []

    def _key(dev):
        serial = getattr(dev, "iSerial", "")
        return serial or "~~~~~"

    return sorted(devices, key=_key)


def parse_lsblk_size(size_str: str) -> float:
    """
    Parse a size string from a command like 'lsblk' (e.g., '465.8G', '14.2T', '500M')
    and return the size in gigabytes. Returns 0.0 if the string cannot be parsed.

    Args:
        size_str (str): The size string to parse.

    Returns:
        float: The parsed size in gigabytes, or 0.0 if parsing fails.
    """
    size_str = size_str.strip().upper()
    match = re.match(r"([\d\.]+)([GMTEK]?)", size_str)
    if not match:
        return 0.0

    numeric_part, unit = match.groups()
    try:
        val = float(numeric_part)
    except ValueError:
        return 0.0

    # Convert to GB
    if unit == "G":
        return val
    elif unit == "M":
        return val / 1024
    elif unit == "T":
        return val * 1024
    elif unit == "K":
        return val / (1024**2)
    elif unit == "E":  # Exabytes (unlikely, but let's handle it)
        return val * (1024**2)
    else:
        # No recognized suffix means "bytes" or can't parse -> treat as bytes
        # If truly bytes, val is likely large -> convert to GB
        return bytes_to_gb(val)


# -----------------------------------------------------------
# Gather block device info: name, serial, size (converted to GB)
# -----------------------------------------------------------
def list_usb_drives():
    """
    Uses the 'system_profiler' command to retrieve information about USB devices
    and extracts relevant details for connected USB drives, particularly focusing
    on Apricorn devices.

    Returns:
        List[dict]: A list of dictionaries, where each dictionary contains
                     information about a USB drive (if identified as an Apricorn
                     device) including its name, serial number (if available),
                     and size in bytes. Returns an empty list if no Apricorn
                     USB drives are found or if the 'system_profiler' command fails.
    """
    cmd = ["system_profiler", "SPUSBDataType", "-json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    else:
        usb_drives = json.loads(result.stdout)
        obj=usb_drives["SPUSBDataType"]
        matches = []

        def recurse(obj=usb_drives["SPUSBDataType"]):
            if isinstance(obj, dict):
                # Check vendor_id
                vendor_id = obj.get('vendor_id', '')
                if '0984' in vendor_id:
                    matches.append(obj)
                # Recurse into all dictionary values
                for value in obj.values():
                    recurse(value)
            elif isinstance(obj, list):
                # Recurse into list elements
                for item in obj:
                    recurse(item)

        recurse()
        pprint(matches)
        return matches


def parse_uasp_info():
    uas_dict = {}
    
    # Get the list of all USB drives detected by system_profiler
    all_drives = list_usb_drives()

    for drive in all_drives:
        product_name = drive.get('_name')
        bsd_name = None
        if 'Media' in drive and len(drive['Media']) > 0:
            bsd_name = drive['Media'][0].get('bsd_name')

        if product_name and bsd_name:
            cmd = ["diskutil", "info", bsd_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            is_uas = False
            if result.returncode == 0:
                # Check for "Protocol: USB" and "Transport: UAS"
                if "Protocol: USB" in result.stdout and "Transport: UAS" in result.stdout:
                    is_uas = True
            
            uas_dict[product_name] = is_uas
            
    pprint(uas_dict)
    return uas_dict


# ------------------------------------------------------
# Enumerate devices, filter for Apricorn, gather details
# ------------------------------------------------------
def find_apricorn_device() -> Optional[List[macOSUsbDeviceInfo]]:
    """
    Identifies connected Apricorn USB devices and gathers detailed information
    about them, including USB descriptors, product information, and whether
    they are using UAS. It then maps this information to the `macOSUsbDeviceInfo`
    dataclass.

    Returns:
        Optional[List[macOSUsbDeviceInfo]]: A list of `macOSUsbDeviceInfo` objects,
                                             each representing an Apricorn USB device
                                             found on the system. Returns None if no
                                             Apricorn devices are detected or if
                                             necessary commands fail.
    """
    # Collect drive info once
    all_drives = list_usb_drives()  # lsblk
    # target_disk = list_disk_partitions() #fdisk
    apricorn_hardware = parse_uasp_info()  # lshw

    lsusb_cmd = ["lsusb"]
    result = subprocess.run(lsusb_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    apricorn_devices = []
    for key, value in apricorn_hardware.items():
        for drive in all_drives:
            if key == drive["_name"]:
                if int(drive["bus_power"]) > 500:
                    bcdUSB_str = 3
                else:
                    bcdUSB_str = 2
                idVendor_str = drive["vendor_id"].replace("0x", "")[:4]
                idProduct_str = drive["product_id"].replace("0x", "")
                bcdDevice_str = drive["bcd_device"].replace(".", "")
                iManufacturer_str = drive["manufacturer"]
                iProduct_str = drive["_name"]
                iSerial_str = drive["serial_num"]
                SCSIDevice_str = value
                drive_size_str = find_closest(
                    bytes_to_gb(drive["Media"][0]["size_in_bytes"]),
                    closest_values[idProduct_str][1],
                )
                # Safely get the removable_media value from the nested dictionary
                removable_val = "unknown"
                try:
                    removable_val = drive["Media"][0].get("removable_media", "unknown")
                except (IndexError, KeyError, TypeError):
                    pass  # Ignore if Media key or list is missing

                media_type = "Unknown"
                if removable_val == "yes":
                    media_type = "Removable Media"
                elif removable_val == "no":
                    media_type = "Basic Disk"

                # Best-effort: version information is not resolved on macOS enumeration yet
                dev_info = macOSUsbDeviceInfo(
                    bcdUSB=bcdUSB_str,
                    idVendor=idVendor_str,
                    idProduct=idProduct_str,
                    bcdDevice=f"0{bcdDevice_str}",
                    iManufacturer=iManufacturer_str,
                    iProduct=iProduct_str,
                    iSerial=iSerial_str,
                    SCSIDevice=SCSIDevice_str,
                    driveSizeGB=drive_size_str or 0,
                    mediaType=media_type,
                    # Leave version fields as N/A unless a safe disk mapping is added later
                )
                # Remove version fields if bridgeFW doesn't match bcdDevice (device can't report reliably)
                try:

                    def _norm_hex4(s: object) -> str | None:
                        if s is None:
                            return None
                        ss = str(s).strip()
                        ss = ss.replace("0x", "").replace("0X", "").replace(".", "")
                        ss = re.sub(r"[^0-9a-fA-F]", "", ss)
                        if not ss:
                            return None
                        if len(ss) > 4:
                            ss = ss[-4:]
                        return ss.lower().zfill(4)

                    _bd = _norm_hex4(getattr(dev_info, "bcdDevice", None))
                    _bf = _norm_hex4(getattr(dev_info, "bridgeFW", None))
                    if _bd is None or _bf is None or _bd != _bf:
                        for _k in (
                            "scbPartNumber",
                            "hardwareVersion",
                            "modelID",
                            "mcuFW",
                        ):
                            try:
                                delattr(dev_info, _k)
                            except Exception:
                                pass
                except Exception:
                    # If sanitization fails, leave object as-is
                    pass
                apricorn_devices.append(dev_info)

    return apricorn_devices if apricorn_devices else None


# ---------------
# Example Usage
# ---------------
def main(find_apricorn_device=None):
    """
    Main function to find and display information about connected Apricorn devices.

    Args:
        find_apricorn_device (callable): A function that returns a list of
                                         macOSUsbDeviceInfo objects representing
                                         connected Apricorn devices.
    """
    finder = (
        find_apricorn_device
        if find_apricorn_device is not None
        else globals().get("find_apricorn_device")
    )
    devices = finder() if callable(finder) else None
    if not devices:
        print("No Apricorn devices found.")
    else:
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            _printable = dict(dev.__dict__)
            _printable.pop("bridgeFW", None)
            for field_name, value in _printable.items():
                print(f"  {field_name}: {value}")


if __name__ == "__main__":
    main(find_apricorn_device)
