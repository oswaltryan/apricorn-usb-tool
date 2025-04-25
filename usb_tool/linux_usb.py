#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass, field
from typing import List, Optional
import json
from pprint import pprint

# -----------------------------
# Same Dataclass as on Windows
# -----------------------------
@dataclass
class LinuxUsbDeviceInfo:
    """Dataclass mirroring the Windows USB device info structure for Linux."""
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
    blockDevice: str = ""

# ----------------
# Size Conversions
# ----------------
def bytes_to_gb(bytes_value: float) -> float:
    """Convert a value in bytes to gigabytes."""
    return bytes_value / (1024 ** 3)

def parse_lsblk_size(size_str: str) -> float:
    """
    Parse a size string from the 'lsblk' command output (e.g., '465.8G', '14.2T', '500M')
    and return the size in gigabytes as a float. Returns 0.0 if the string is unparsable.
    """
    size_str = size_str.strip().upper()
    match = re.match(r'([\d\.]+)([GMTEK]?)', size_str)
    if not match:
        return 0.0

    numeric_part, unit = match.groups()
    try:
        val = float(numeric_part)
    except ValueError:
        return 0.0

    # Convert to GB
    if unit == 'G':
        return val
    elif unit == 'M':
        return val / 1024
    elif unit == 'T':
        return val * 1024
    elif unit == 'K':
        return val / (1024**2)
    elif unit == 'E':  # Exabytes (unlikely, but let's handle it)
        return val * (1024**2)
    else:
        # No recognized suffix means "bytes" or can't parse -> treat as bytes
        # If truly bytes, val is likely large -> convert to GB
        return bytes_to_gb(val)

def find_closest(target: float, options: List[int]) -> int:
    """
    Find the integer value in the list `options` that is closest to the float `target`.
    Returns the closest integer.
    """
    return min(options, key=lambda x: abs(x - target))

# -----------------------------------------------------------
# Gather block device info: name, serial, size (converted to GB)
# -----------------------------------------------------------
def list_usb_drives():
    """
    Lists USB drives using the 'lsblk' command and extracts their serial number and size.
    Returns a list of dictionaries, where each dictionary contains the 'serial' (string)
    and 'size_gb' (float) of a USB drive. Only drives with a 12-character serial number are included.
    """
    cmd = ["lsblk", "-n", "-o", "NAME,SERIAL,SIZE", "-d"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    drives_info = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue

        name, serial, size_str = parts
        # If there's no serial, skip
        if not serial or serial == '-' or len(serial) != 12:
            continue

        size_gb = parse_lsblk_size(size_str)
        drives_info.append({
            "serial": serial,
            "size_gb": size_gb
        })
    # print("lsblk:")
    # pprint(drives_info)
    # print()
    return drives_info

def list_disk_partitions():
    """
    Uses the 'fdisk' command to list partitions for /dev/sda through /dev/sdn.
    It filters out entries that contain "Flash Disk" in their output.
    Returns a list of lists, where each inner list contains the device path (e.g., '/dev/sda')
    and the raw output of the 'fdisk -l' command for that device.
    """
    target_disk = []
    targets = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n']
    for disk in targets:
        cmd = ["sudo", "fdisk", "-l", f"/dev/sd{disk}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            continue
        else:
            if "Flash Disk" in result.stdout:
                continue
            target_disk.append([f"/dev/sd{disk}", result.stdout])
    # print("fdisk:")
    # pprint(target_disk)
    # print()
    return target_disk

def parse_uasp_info():
    """
    Uses the 'lshw' command to retrieve information about disk and storage devices in JSON format.
    It then filters this information to identify Apricorn USB devices and checks if they are using the 'uas' driver (UASP).
    Returns a list of dictionaries, where each dictionary contains information about an Apricorn USB device.
    """
    uasp_devices = []
    cmd = ["sudo", "lshw", "-class", "disk", "-class", "storage", "-json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return result
    else:
        uasp_devices = json.loads(result.stdout)
        apricorn_devices = []
        for item in range(len(uasp_devices) -1, -1, -1):
            if 'businfo' not in uasp_devices[item]:
                uasp_devices.pop(item)
        for item in range(len(uasp_devices)):
            if 'vendor' not in uasp_devices[item].keys() or uasp_devices[item]['version'] == '1.33': # Exclude SATAWire
                continue
            if uasp_devices[item]['vendor'] == "Apricorn":
                if 'usb' in uasp_devices[item]['businfo']:
                    apricorn_devices.append(uasp_devices[item])
        # print("lshw:")
        # pprint(apricorn_devices)
        # print()
        return apricorn_devices

# ---------------------------------------
# Helpers: parse USB version & placeholders
# ---------------------------------------
def parse_usb_version(usb_str: str) -> str:
    """
    Parses a USB version string, attempting to handle both direct version numbers (e.g., '3.20')
    and BCD-formatted version numbers (e.g., '0x0320'). If a BCD format is detected, it converts
    it to a human-readable format (e.g., 3.20). If parsing fails, it returns the original string.
    """
    if re.match(r'^\d+\.\d+$', usb_str):
        return usb_str
    try:
        bcd = int(usb_str, 16)
        major = (bcd & 0xFF00) >> 8
        minor = (bcd & 0x00F0) >> 4
        subminor = bcd & 0x000F
        if subminor:
            return f"{major}.{minor}{subminor}"
        return f"{major}.{minor}"
    except ValueError:
        return usb_str

# -----------------------------
# Parse "lsusb -v -d <vid:pid>"
# -----------------------------
def parse_lsusb_output(vid: str, pid: str) -> dict:
    """
    Runs the command 'lsusb -v -d vid:pid' and parses the output to extract relevant USB
    descriptor information. Returns a dictionary containing the extracted information
    (e.g., bcdUSB, idVendor, iProduct, iSerial). Returns an empty dictionary if the command
    fails or the output cannot be parsed.
    """
    cmd = ["lsusb", "-v", "-d", f"{vid}:{pid}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}

    output = result.stdout
    # pprint(output)
    data = {}

    for line in output.splitlines():
        line = line.strip()

        # bcdUSB or bcdDevice
        m = re.match(r'^(bcdUSB|bcdDevice)\s+([\da-fx\.]+)', line, re.IGNORECASE)
        if m:
            data[m.group(1)] = m.group(2)
            continue

        # e.g.:
        #   idVendor           0x0984  Apricorn
        #   iProduct                2   Aegis Secure Key
        m = re.match(r'^(idVendor|idProduct)\s+(0x[\da-fA-F]+)\s+(.+)', line)
        if m:
            key, val, text = m.groups()
            data[key] = val  # keep hex string e.g. "0x0984"
            if key == "idVendor":
                data["iManufacturer"] = text.strip()
            elif key == "idProduct":
                data["iProduct"] = text.strip()
            continue

        # iManufacturer / iProduct / iSerial lines
        #   iManufacturer           1   Apricorn
        #   iProduct                2   Aegis Secure Key
        #   iSerial                 3   1234567890
        m = re.match(r'^(iManufacturer|iProduct|iSerial)\s+\d+\s+(.+)', line)
        if m:
            data[m.group(1)] = m.group(2).strip()
            continue

    return data

# ------------------------------------------------------
# Enumerate "lsusb", filter for Apricorn, gather details
# ------------------------------------------------------
def find_apricorn_device() -> Optional[List[LinuxUsbDeviceInfo]]:
    """
    Enumerates USB devices using 'lsusb', filters for Apricorn devices (vendor ID 0984),
    and gathers detailed information for each found device using 'lsusb -v -d'.
    It then correlates this information with drive size information obtained from 'lsblk'
    and UASP status from 'lshw'. Finally, it returns a list of LinuxUsbDeviceInfo objects
    representing the detected Apricorn devices. Devices with product IDs 0221 and 0301 are excluded.
    """
    closest_values = {
        "0310": ["Padlock 3.0", [256, 500, 1000, 2000, 4000, 8000, 16000]],
        "0315": ["Padlock DT", [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000]],
        "0351": ["Aegis Portable", [128, 256, 500, 1000, 2000, 4000, 8000, 12000, 16000]],
        "1400": ["Fortress", [256, 500, 1000, 2000, 4000, 8000, 16000]],
        "1405": ["Padlock SSD", [240, 480, 1000, 2000, 4000]],
        "1406": ["Padlock DT FIPS", [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000]],
        "1407": ["Secure Key 3.0", [16, 30, 60, 120, 240, 480, 1000, 2000, 4000]],
        "1408": ["Fortress L3", [500, 512, 1000, 2000, 4000, 5000, 8000, 16000, 20000]],
        "1409": ["Secure Key 3.0", [16, 32, 64, 128]],
        "1410": ["Secure Key 3.0", [4, 8, 16, 32, 64, 128, 256, 512]],
        "1413": ["Padlock NVX", [500, 1000, 2000]]}
        
    # Collect drive info once
    all_drives = list_usb_drives()
    target_disk = list_disk_partitions()
    apricorn_hardware = parse_uasp_info()

    lsusb_cmd = ["lsusb"]
    result = subprocess.run(lsusb_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    apricorn_devices = []
    for line in result.stdout.splitlines():
        # typical: "Bus 001 Device 002: ID 0984:0035 Apricorn Corp."
        match = re.match(r'^Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F]+):([0-9a-fA-F]+)\s+(.*)', line.strip())
        if not match:
            continue
        bus, dev, vid, pid, tail = match.groups()

        # Filter for Apricorn=0984, skip 0351
        vid_lower = vid.lower()
        pid_lower = pid.lower()
        if vid_lower != "0984" or pid_lower == "0221" or pid_lower == "0301": # Exclude SATAWire and 4GB keys
            continue

        info_dict = parse_lsusb_output(vid_lower, pid_lower)
        if not info_dict:
            # fallback if -v fails or no permission
            info_dict = {
                "idVendor": f"0x{vid_lower}",
                "idProduct": f"0x{pid_lower}",
                "iManufacturer": tail,  # partial glean
                "iProduct": tail
            }

        # Normalize
        idVendor_str = info_dict.get("idVendor", f"0x{vid_lower}").lower().replace("0x", "")
        idProduct_str = info_dict.get("idProduct", f"0x{pid_lower}").lower().replace("0x", "")
        bcdUSB_str = parse_usb_version(info_dict.get("bcdUSB", "0"))
        bcdDevice_str = info_dict.get("bcdDevice", "0000").lower().replace("0x", "").replace('.', '')
        iManufacturer_str = info_dict.get("iManufacturer", "").strip()
        iProduct_str = info_dict.get("iProduct", "").strip()
        SCSIDevice_str = "N/A"
        iSerial_str = info_dict.get("iSerial", "").strip()
        if len(iSerial_str) != 12:
            iSerial_str = iSerial_str[:-12]


        # Match the iSerial to the "serial" from lsblk
        matched_drive = next(
            (d for d in all_drives if iSerial_str and iSerial_str in d["serial"]),
            None
        )
        drive_size_str = find_closest(matched_drive['size_gb'], closest_values[idProduct_str][1]) if matched_drive else "N/A"


        # Match block device
        if target_disk == []:
            blockDevice_str = "N/A"
        for disk in target_disk:
            if iProduct_str in disk[1]:
                blockDevice_str = disk[0]

        # Match UASP info
        for device in apricorn_hardware:
            if device['serial'] == iSerial_str:
                if device['configuration']['driver'] == "uas":
                    SCSIDevice_str = True
                else:
                    SCSIDevice_str = False

        dev_info = LinuxUsbDeviceInfo(
            bcdUSB=bcdUSB_str,
            idVendor=idVendor_str,
            idProduct=idProduct_str,
            bcdDevice=f"0{bcdDevice_str}",
            iManufacturer=iManufacturer_str,
            iProduct=iProduct_str,
            iSerial=iSerial_str,
            SCSIDevice=SCSIDevice_str,  # placeholder
            driveSizeGB=drive_size_str,
            # usbController="",  # placeholder
            blockDevice=blockDevice_str
        )
        apricorn_devices.append(dev_info)

    return apricorn_devices if apricorn_devices else None

# ---------------
# Example Usage
# ---------------
def main(find_apricorn_device):
    """
    Main function to find and display information about connected Apricorn devices.

    Args:
        find_apricorn_device (callable): A function that returns a list of
                                         macOSUsbDeviceInfo objects representing
                                         connected Apricorn devices.
    """
    devices = find_apricorn_device()
    if not devices:
        print("No Apricorn devices found.")
    else:
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            for field_name, value in dev.__dict__.items():
                print(f"  {field_name}: {value}")

if __name__ == "__main__":
    main(find_apricorn_device)
