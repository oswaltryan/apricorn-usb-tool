#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional
import json

from .device_config import closest_values
from .utils import bytes_to_gb, find_closest


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
        # pprint(usb_drives)
        # print()
        drives_info = []
        for drive in range(len(usb_drives["SPUSBDataType"])):
            if len(usb_drives["SPUSBDataType"][drive].keys()) < 3:
                continue
            if "Media" not in usb_drives["SPUSBDataType"][drive]["_items"][0].keys():
                continue
            if (
                usb_drives["SPUSBDataType"][drive]["_items"][0]["manufacturer"]
                == "Apricorn"
            ):
                drives_info.append(usb_drives["SPUSBDataType"][drive]["_items"][0])
        # pprint(drives_info)
        return drives_info


def parse_uasp_info():
    """
    Uses the 'ioreg' command to identify USB devices that are using the
    USB Attached SCSI Protocol (UASP).

    Returns:
        dict: A dictionary where keys are the product names of USB devices
              and values are boolean indicating whether the device is using UAS
              (True) or not (False).
    """
    cmd = r"""
ioreg -p IOUSB -w0 -l | awk '
/"USB Product Name"/ { product=$0 }
/"IOClass"/ {
    if ($3 == "\"IOUSBAttachedSCSI\"") {
        uas=1
    } else {
        uas=0
    }
    if (product && uas >= 0) {
        gsub(/.*= /, "", product)
        gsub(/"/, "", product)
        print product ": " (uas ? "UAS" : "Not UAS")
        product=""
        uas=-1
    }
}' | sort
"""
    result = subprocess.run(["zsh", "-c", cmd], capture_output=True, text=True)
    uas_dict = {}
    for line in result.stdout.strip().splitlines():
        if ": " in line:
            name, status = line.strip().split(": ")
            uas_dict[name] = status == "UAS"

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
                )
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
            for field_name, value in dev.__dict__.items():
                print(f"  {field_name}: {value}")


if __name__ == "__main__":
    main(find_apricorn_device)
