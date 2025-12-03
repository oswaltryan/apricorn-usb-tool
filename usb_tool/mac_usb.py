#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional, Union
import json

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
    driveSizeGB: Union[int, str] = 0
    blockDevice: str = ""
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
        matches = []

        def recurse(obj=usb_drives["SPUSBDataType"]):
            if isinstance(obj, dict):
                # Check vendor_id
                vendor_id = obj.get("vendor_id", "")
                manufacturer = obj.get("manufacturer", "")
                if "0984" in vendor_id or "Apricorn" in manufacturer:
                    matches.append(obj)
                # Recurse into all dictionary values
                for value in obj.values():
                    recurse(value)
            elif isinstance(obj, list):
                # Recurse into list elements
                for item in obj:
                    recurse(item)

        recurse()
        #        pprint(matches)
        return matches


def parse_uasp_info():
    uas_dict = {}

    # Get the list of all USB drives detected by system_profiler
    all_drives = list_usb_drives()

    for drive in all_drives:
        product_name = drive.get("_name")
        bsd_name = None
        if "Media" in drive and len(drive["Media"]) > 0:
            bsd_name = drive["Media"][0].get("bsd_name")

        if product_name and bsd_name:
            cmd = ["diskutil", "info", bsd_name]
            result = subprocess.run(cmd, capture_output=True, text=True)

            is_uas = False
            if result.returncode == 0:
                # Check for "Protocol: USB" and "Transport: UAS"
                if (
                    "Protocol: USB" in result.stdout
                    and "Transport: UAS" in result.stdout
                ):
                    is_uas = True

            uas_dict[product_name] = is_uas

    #    pprint(uas_dict)
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
    all_drives = list_usb_drives()
    apricorn_uas_status = parse_uasp_info()
    # target_disk = list_disk_partitions() #fdisk

    apricorn_devices = []
    for drive in all_drives:
        product_name = drive.get("_name")
        if product_name:
            # Default to False if not found in apricorn_uas_status (e.g., OOB mode)
            is_uas = apricorn_uas_status.get(product_name, False)

            bcdUSB_str = 3 if int(drive.get("bus_power", "0")) > 500 else 2
            idVendor_str = drive.get("vendor_id", "").replace("0x", "")[:4]
            idProduct_str = drive.get("product_id", "").replace("0x", "")
            bcdDevice_str = drive.get("bcd_device", "").replace(".", "")
            iManufacturer_str = drive.get("manufacturer", "")
            iProduct_str = drive.get("_name", "")
            iSerial_str = drive.get("serial_num", "")

            drive_size_gb: Union[int, str] = 0
            media_type = "Unknown"

            if "Media" in drive and len(drive["Media"]) > 0:
                media_info = drive["Media"][0]
                size_in_bytes = media_info.get("size_in_bytes", 0)
                approx_size = find_closest(
                    bytes_to_gb(size_in_bytes),
                    closest_values.get(idProduct_str, (0, [0]))[1],
                )
                drive_size_gb = approx_size if approx_size is not None else 0

                removable_val = media_info.get("removable_media", "unknown")
                if removable_val == "yes":
                    media_type = "Removable Media"
                elif removable_val == "no":
                    media_type = "Basic Disk"
                bsd_name = media_info.get("bsd_name", "")
            else:
                drive_size_gb = "N/A (OOB Mode)"
                media_type = "Unknown"
                bsd_name = ""

            # --- Best-effort Device Version Info (UPDATED Logic) ---
            scb_part = "N/A"
            hw_ver = "N/A"
            model_id = "N/A"
            mcu_fw_str = "N/A"
            bridge_fw = "N/A"

            # Check if we have a bsd_name to target (e.g., "disk2")
            if query_device_version is not None and bsd_name:
                # macOS query expects a path like /dev/disk2
                device_path = f"/dev/{bsd_name}"
                try:
                    _ver = query_device_version(device_path)

                    # 1. Try standard attribute access
                    if getattr(_ver, "scb_part_number", ""):
                        scb_part = _ver.scb_part_number
                    if getattr(_ver, "hardware_version", None):
                        hw_ver = _ver.hardware_version or "N/A"
                    if getattr(_ver, "model_id", None):
                        model_id = _ver.model_id or "N/A"
                    mj, mn, sb = getattr(_ver, "mcu_fw", (None, None, None))
                    if mj is not None and mn is not None and sb is not None:
                        mcu_fw_str = f"{mj}.{mn}.{sb}"
                    if getattr(_ver, "bridge_fw", None):
                        bridge_fw = _ver.bridge_fw or "N/A"

                    # 2. Fallback Parsing for OOB Mode
                    # Check for .raw_data (preferred) or .raw (ctypes fallback)
                    raw_bytes = None
                    if hasattr(_ver, "raw_data"):
                        raw_bytes = bytes(_ver.raw_data)
                    elif hasattr(_ver, "raw"):
                        raw_bytes = bytes(_ver.raw)

                    if scb_part == "N/A" and raw_bytes:
                        try:
                            if len(raw_bytes) >= 4:
                                bridge_fw = f"{raw_bytes[2]:02x}{raw_bytes[3]:02x}"

                            match = re.search(rb"(\d{2})-(\d{11})", raw_bytes)
                            if match:
                                p1_str = match.group(1).decode("utf-8")
                                p2_str = match.group(2).decode("utf-8")
                                scb_part = f"{p1_str}-{p2_str[:4]}"
                                digits = [int(c) for c in p2_str]
                                if len(digits) >= 11:
                                    model_id = f"{digits[4]}{digits[5]}"
                                    hw_ver = f"{digits[6]}.{digits[7]}"
                                    mcu_fw_str = f"{digits[8]}.{digits[9]}.{digits[10]}"
                        except Exception:
                            pass
                except Exception:
                    pass

            dev_info = macOSUsbDeviceInfo(
                bcdUSB=bcdUSB_str,
                idVendor=idVendor_str,
                idProduct=idProduct_str,
                bcdDevice=f"0{bcdDevice_str}" if bcdDevice_str else "N/A",
                iManufacturer=iManufacturer_str,
                iProduct=iProduct_str,
                iSerial=iSerial_str,
                SCSIDevice=is_uas,
                driveSizeGB=drive_size_gb,
                blockDevice=bsd_name,
                mediaType=media_type,
                scbPartNumber=scb_part,
                hardwareVersion=hw_ver,
                modelID=model_id,
                mcuFW=mcu_fw_str,
                bridgeFW=bridge_fw,
            )

            # --- VALIDATION AND CLEANUP LOGIC ---
            if getattr(dev_info, "scbPartNumber", "N/A") == "N/A":
                for _k in ("scbPartNumber", "hardwareVersion", "modelID", "mcuFW"):
                    try:
                        delattr(dev_info, _k)
                    except Exception:
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
