#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass, field
from typing import List, Optional

# -----------------------------
# Same Dataclass as on Windows
# -----------------------------
@dataclass
class LinuxUsbDeviceInfo:
    """Dataclass mirroring the Windows USB device info structure."""
    idProduct: str
    idVendor: str
    bcdDevice: str
    bcdUSB: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    device_id: str
    vendor: str
    usb_protocol: str
    usbController: str = ""
    SCSIDevice: str = ""
    driveSize: str = ""
    blockDevice: str = ""

# ----------------
# Size Conversions
# ----------------
def bytes_to_gb(bytes_value: float) -> float:
    """Convert bytes to gigabytes."""
    return bytes_value / (1024 ** 3)

def parse_lsblk_size(size_str: str) -> float:
    """
    Parse a size string from lsblk (e.g., '465.8G', '14.2T', '500M') and return size in GB.
    Default to 0 if unparsable.
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
    """Find the closest integer value in `options` to the float `target`."""
    return min(options, key=lambda x: abs(x - target))

# ----------------------------------------------
# Known thresholds to mirror your Windows logic
# ----------------------------------------------
closest_values = [16, 30, 60, 120, 240, 480, 1000, 2000]

# -----------------------------------------------------------
# Gather block device info: name, serial, size (converted to GB)
# -----------------------------------------------------------
def list_usb_drives():
    """
    Return a list of dictionaries with { 'serial': str, 'size_gb': float, 'closest_match': int }
    from lsblk. We only parse "SERIAL" if it exists. Typically, USB flash drives etc. show up here.
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
        if not serial or serial == '-':
            continue

        size_gb = parse_lsblk_size(size_str)
        closest_match = find_closest(size_gb, closest_values)
        drives_info.append({
            "serial": serial,
            "size_gb": size_gb,
            "closest_match": closest_match
        })
    return drives_info

# ---------------------------------------
# Helpers: parse USB version & placeholders
# ---------------------------------------
def parse_usb_version(usb_str: str) -> str:
    """
    Attempt to mirror the Windows logic for version formatting.
    Windows code parses bcdUSB as BCD (e.g., 0x0320 -> 3.20).
    If lsusb gives '3.20' or '2.00' directly, keep it as-is;
    else do a best-effort parse.
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
    Run 'lsusb -v -d vid:pid' and parse relevant descriptor info
    into a dictionary. Return empty if we can't parse or permissions fail.
    """
    cmd = ["lsusb", "-v", "-d", f"{vid}:{pid}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}

    output = result.stdout
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
def find_apricorn_device() -> Optional[List[WinUsbDeviceInfo]]:
    """
    Replicates your Windows 'find_apricorn_device' logic in Linux:
    1) "lsusb" short listing
    2) Filter for vendor=0984, exclude product=0351
    3) parse descriptors with parse_lsusb_output
    4) correlate with drive size from lsblk
    5) return a list of WinUsbDeviceInfo
    """
    # Collect drive info once
    all_drives = list_usb_drives()

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
        if vid_lower != "0984" or pid_lower == "0351":
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
        bcdDevice_str = info_dict.get("bcdDevice", "0000").lower().replace("0x", "")
        iManufacturer_str = info_dict.get("iManufacturer", "").strip()
        iProduct_str = info_dict.get("iProduct", "").strip()
        iSerial_str = info_dict.get("iSerial", "").strip()

        device_id_str = f"USB\\VID_{idVendor_str}&PID_{idProduct_str}\\{iSerial_str}"

        # Match the iSerial to the "serial" from lsblk
        matched_drive = next(
            (d for d in all_drives if iSerial_str and iSerial_str in d["serial"]),
            None
        )
        drive_size_str = str(matched_drive["closest_match"]) if matched_drive else "N/A"

        dev_info = WinUsbDeviceInfo(
            idProduct=idProduct_str,
            idVendor=idVendor_str,
            bcdDevice=bcdDevice_str,
            bcdUSB=bcdUSB_str,
            iManufacturer=iManufacturer_str,
            iProduct=iProduct_str,
            iSerial=iSerial_str,
            device_id=device_id_str,
            vendor=iManufacturer_str,   # same as Windows code
            usbController="",  # placeholder
            SCSIDevice="False",  # placeholder
            driveSize=drive_size_str
        )
        apricorn_devices.append(dev_info)

    return apricorn_devices if apricorn_devices else None

# ---------------
# Example Usage
# ---------------
def main(find_apricorn_device):
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
