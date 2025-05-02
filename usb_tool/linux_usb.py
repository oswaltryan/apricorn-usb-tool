#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass, field
from typing import List, Optional
import json
from pprint import pprint
import os # Added for path checks
import sys # Added missing import

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
    driveSizeGB: int = 0 # Keep as int for consistency, handle N/A during assignment
    # usbController: str = "" # Removed, not easily available/reliable on Linux
    blockDevice: str = "" # Added block device path (e.g., /dev/sdx)

# ----------------
# Size Conversions
# ----------------
def bytes_to_gb(bytes_value: float) -> float:
    """Convert a value in bytes to gigabytes."""
    # Handle potential None or non-numeric input gracefully
    if not isinstance(bytes_value, (int, float)) or bytes_value <= 0:
        return 0.0
    return bytes_value / (1024 ** 3)

def parse_lsblk_size(size_str: str) -> float:
    """
    Parse a size string from the 'lsblk' command output (e.g., '465.8G', '14.2T', '500M')
    and return the size in gigabytes as a float. Returns 0.0 if the string is unparsable.
    """
    if not size_str: return 0.0
    size_str = size_str.strip().upper()
    # More robust regex to handle potential commas or other chars
    match = re.match(r'([\d\.,]+)\s*([GMTEK])?', size_str)
    if not match:
        return 0.0

    numeric_part, unit = match.groups()
    # Clean up numeric part (remove commas)
    numeric_part = numeric_part.replace(',', '')

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
        # Assume bytes if no unit or unrecognized unit
        return bytes_to_gb(val)

def find_closest(target: float, options: List[int]) -> Optional[int]:
    """
    Find the integer value in the list `options` that is closest to the float `target`.
    Returns the closest integer or None if target or options are invalid.
    """
    if not isinstance(target, (int, float)) or target <= 0 or not options:
        return None
    try:
        return min(options, key=lambda x: abs(x - target))
    except (TypeError, ValueError): # Catch issues if options are not numbers
        return None

# -----------------------------------------------------------
# Gather block device info: name, serial, size (converted to GB)
# -----------------------------------------------------------
def list_usb_drives():
    """
    Lists USB drives using the 'lsblk' command and extracts their serial number,
    size, and device name.
    Returns a list of dictionaries, where each dictionary contains 'name' (str, e.g., sda),
    'serial' (string), and 'size_gb' (float).
    Only drives with a 12-character serial number are included.
    Handles potential errors during subprocess execution.
    """
    # -p includes full path /dev/..., -l provides list format
    cmd = ["lsblk", "-p", "-o", "NAME,SERIAL,SIZE", "-d", "-n", "-l"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False) # Don't check return code here
        if result.returncode != 0:
            print(f"Warning: 'lsblk' command failed with code {result.returncode}. Stderr: {result.stderr.strip()}", file=sys.stderr)
            return []
        if not result.stdout.strip():
             # print("Warning: 'lsblk' command returned no output.", file=sys.stderr)
             return [] # Handle case where lsblk runs but finds nothing
    except FileNotFoundError:
        print("Error: 'lsblk' command not found. Cannot determine drive sizes or paths.", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error running 'lsblk': {e}", file=sys.stderr)
        return []

    drives_info = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Expecting NAME SERIAL SIZE format
        parts = line.split(None, 2)
        if len(parts) < 3:
            # print(f"Warning: Skipping malformed lsblk line: '{line}'") # Debugging
            continue

        name, serial, size_str = parts
        # Check if serial looks valid (12 chars, not placeholder)
        # Apricorn serials are typically 12 hex chars, but let's be flexible if needed.
        # We rely more on matching via lshw later. Keep the 12 char check for now.
        if not serial or serial == '-' or len(serial) != 12:
            continue

        size_gb = parse_lsblk_size(size_str)
        drives_info.append({
            "name": name, # Full path like /dev/sda
            "serial": serial,
            "size_gb": size_gb
        })
    # print("lsblk:")
    # pprint(drives_info)
    # print()
    return drives_info

def list_disk_partitions():
    """
    Uses the 'fdisk' command (requires sudo) to list partitions for /dev/sda through /dev/sdn.
    This seems less reliable for getting the base device associated with an Apricorn drive
    compared to 'lshw' or 'lsblk'. It's currently used to check for "Flash Disk",
    but might not be necessary if other methods work.

    Returns a list of lists, where each inner list contains the device path (e.g., '/dev/sda')
    and the raw output of the 'fdisk -l' command for that device IF it doesn't contain "Flash Disk".
    Returns an empty list if sudo/fdisk fails or no relevant disks are found.
    """
    target_disk = []
    targets = [f'/dev/sd{chr(ord("a") + i)}' for i in range(14)] # /dev/sda to /dev/sdn

    fdisk_path = "/usr/sbin/fdisk" # Common path, adjust if needed
    if not os.path.exists(fdisk_path):
        # print("Warning: 'fdisk' not found at /usr/sbin/fdisk. Skipping partition check.", file=sys.stderr)
        return []

    for disk_path in targets:
        # Check if the block device exists before trying fdisk
        if not os.path.exists(disk_path):
            continue

        cmd = ["sudo", fdisk_path, "-l", disk_path]
        try:
            # Increased timeout, fdisk can sometimes hang on problematic devices
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
        except FileNotFoundError:
             print("Error: 'sudo' command not found. Cannot run fdisk.", file=sys.stderr)
             return [] # Cannot proceed without sudo
        except subprocess.TimeoutExpired:
            print(f"Warning: 'sudo fdisk -l {disk_path}' timed out.", file=sys.stderr)
            continue
        except Exception as e:
             print(f"Error running 'sudo fdisk -l {disk_path}': {e}", file=sys.stderr)
             continue # Skip this disk on error

        # fdisk returns non-zero if no partition table, etc. We care about the output.
        # Check stderr for permission errors first
        if "must be root" in result.stderr.lower() or "permission denied" in result.stderr.lower():
             print(f"Warning: Permission error running 'sudo fdisk -l {disk_path}'. Check sudo setup.", file=sys.stderr)
             # Don't exit, maybe other disks work or listing continues without fdisk info
             continue

        # Check if output contains "Flash Disk" (often indicates non-Apricorn USB key)
        if "Flash Disk" in result.stdout:
            continue

        # If we got output and it wasn't a flash disk, store it
        # Return code 1 is common if disk exists but has no recognized partition table, still useful info maybe
        if result.stdout:
            target_disk.append([disk_path, result.stdout])

    # print("fdisk Results (Non-Flash Disk):")
    # pprint(target_disk)
    # print()
    return target_disk

def parse_uasp_info():
    """
    Uses 'lshw' (requires sudo) to get info about disk/storage devices in JSON.
    Filters for Apricorn USB devices and extracts info like serial, logical name (block device),
    and driver (to infer UASP).

    Returns a list of dictionaries for detected Apricorn USB devices found by lshw,
    including 'serial', 'logicalname' (e.g., /dev/sda), and 'driver' ('uas' or other).
    Returns an empty list on error (e.g., command not found, permission error, JSON parse error).
    """
    lshw_path = "/usr/bin/lshw" # Common path
    if not os.path.exists(lshw_path):
        print("Error: 'lshw' command not found at /usr/bin/lshw. Cannot get detailed hardware info.", file=sys.stderr)
        return []

    cmd = ["sudo", lshw_path, "-class", "disk", "-class", "storage", "-json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
    except FileNotFoundError:
        print("Error: 'sudo' command not found. Cannot run lshw.", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print("Warning: 'sudo lshw ... -json' timed out.", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error running 'sudo lshw ... -json': {e}", file=sys.stderr)
        return []

    if result.returncode != 0:
        # Check stderr for common issues
        if "must be root" in result.stderr.lower() or "permission denied" in result.stderr.lower():
             print("Warning: Permission error running 'sudo lshw'. Check sudo setup. Cannot get detailed hardware info.", file=sys.stderr)
        else:
             print(f"Warning: 'sudo lshw' command failed with code {result.returncode}. Stderr: {result.stderr.strip()}", file=sys.stderr)
        return []

    try:
        all_devices = json.loads(result.stdout)
        if not isinstance(all_devices, list):
             print("Warning: Unexpected JSON format from 'lshw' (expected a list).", file=sys.stderr)
             all_devices = [] # Treat as empty if format is wrong
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON output from 'lshw'.", file=sys.stderr)
        return []

    apricorn_devices_info = []
    for device in all_devices:
        # Ensure it's a dictionary and has necessary keys
        if not isinstance(device, dict): continue

        businfo = device.get('businfo', '')
        vendor = device.get('vendor', '')
        product = device.get('product', '') # Get product name if available
        serial = device.get('serial', '')
        logical_name = device.get('logicalname', '') # This should be the /dev/sdX path
        driver = device.get('configuration', {}).get('driver', '')
        firmware_version = device.get('version', '') # lshw 'version' is often firmware - *** Fixed: Uncommented ***

        # Filter for USB devices from Apricorn
        if 'usb' in businfo and vendor == "Apricorn":
            # Basic sanity check - skip SATAwire adapters if they appear here
            if firmware_version == '1.33': # *** Fixed: Now uses defined variable ***
                continue
            # Ensure we have a serial and logical name for matching
            if serial and logical_name.startswith('/dev/sd'): # Ensure it's a block device path
                 apricorn_devices_info.append({
                     'serial': serial,
                     'logicalname': logical_name,
                     'driver': driver,
                     'product': product # Include product name for potential matching
                 })

    # print("lshw Apricorn Devices Info:")
    # pprint(apricorn_devices_info)
    # print()
    return apricorn_devices_info

# ---------------------------------------
# Helpers: parse USB version & placeholders
# ---------------------------------------
def parse_usb_version(usb_str: str) -> float:
    """
    Parses a USB version string (e.g., '3.20' or BCD '0x0320') into a float (e.g., 3.2).
    Returns 0.0 on failure.
    """
    if not usb_str: return 0.0

    # Handle direct version like "3.0", "2.10"
    if re.match(r'^\d+\.\d+$', usb_str):
        try:
             # Attempt to convert directly, handling potential multi-digit minor/subminor
             parts = usb_str.split('.')
             major = int(parts[0])
             minor_sub = parts[1]
             # Combine minor and subminor for float representation (e.g., "20" -> 0.2)
             float_val = float(f"{major}.{minor_sub}")
             return float_val
        except (ValueError, IndexError):
             pass # Fall through to BCD check

    # Handle BCD format like "0x0300", "0210"
    try:
        # Remove "0x" prefix if present
        if usb_str.lower().startswith('0x'):
            bcd_val = int(usb_str[2:], 16)
        else:
            bcd_val = int(usb_str, 16) # Assume hex if not decimal format above

        major = (bcd_val >> 8) & 0xFF
        minor = (bcd_val >> 4) & 0x0F
        subminor = bcd_val & 0x0F
        # Format as float major.minor (subminor usually ignored for simple float)
        # e.g., 0x0310 -> 3.1, 0x0200 -> 2.0
        float_val = float(f"{major}.{minor}")
        return float_val
    except ValueError:
        # print(f"Warning: Could not parse USB version '{usb_str}'") # Debugging
        return 0.0 # Indicate failure

# -----------------------------
# Parse "lsusb -v -d <vid:pid>"
# -----------------------------
def parse_lsusb_output(vid: str, pid: str) -> dict:
    """
    Runs 'lsusb -v -d vid:pid' (requires permissions, often root) and parses output
    for USB descriptor details.

    Returns a dictionary with keys like 'bcdUSB', 'idVendor', 'idProduct', 'bcdDevice',
    'iManufacturer', 'iProduct', 'iSerial'. Returns empty dict on failure.
    """
    lsusb_path = "/usr/bin/lsusb" # Common path
    if not os.path.exists(lsusb_path):
        # print("Warning: 'lsusb' not found at /usr/bin/lsusb. Cannot get detailed USB descriptors.", file=sys.stderr)
        return {}

    cmd = [lsusb_path, "-v", "-d", f"{vid}:{pid}"]
    try:
        # Needs permissions for -v, might fail without sudo
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
    except subprocess.TimeoutExpired:
        print(f"Warning: '{lsusb_path} -v -d {vid}:{pid}' timed out.", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"Error running '{lsusb_path} -v -d {vid}:{pid}': {e}", file=sys.stderr)
        return {}

    # lsusb -v often returns non-zero if device disconnects during query, or permission errors
    if result.returncode != 0:
         if "could not open" in result.stderr.lower() or "permission denied" in result.stderr.lower():
             pass # Expected if not root, don't flood warnings
             # print(f"Info: Insufficient permissions for 'lsusb -v -d {vid}:{pid}'. Detailed descriptors unavailable.", file=sys.stderr)
         elif "not found" in result.stderr.lower():
             pass # Device might have disconnected
         else:
             # Log other errors if they occur
             print(f"Warning: '{lsusb_path} -v -d {vid}:{pid}' failed (code {result.returncode}). Stderr: {result.stderr.strip()}", file=sys.stderr)
         return {} # Return empty on any failure

    output = result.stdout
    data = {}
    # Use regex with re.IGNORECASE for flexibility
    # Capture hex values and text descriptions where available

    # --- Standard Descriptor Fields ---
    # bcdUSB and bcdDevice
    bcd_match = re.search(r'bcdUSB\s+([\d\.xXa-fA-F]+)', output, re.IGNORECASE)
    if bcd_match: data['bcdUSB'] = bcd_match.group(1).strip()
    bcd_dev_match = re.search(r'bcdDevice\s+([\d\.xXa-fA-F]+)', output, re.IGNORECASE)
    if bcd_dev_match: data['bcdDevice'] = bcd_dev_match.group(1).strip()

    # idVendor and idProduct (with text if available)
    id_vendor_match = re.search(r'idVendor\s+(0x[0-9a-fA-F]+)\s*(.*)', output, re.IGNORECASE)
    if id_vendor_match:
        data['idVendor'] = id_vendor_match.group(1).strip()
        if id_vendor_match.group(2): data['iManufacturer_desc'] = id_vendor_match.group(2).strip()
    id_product_match = re.search(r'idProduct\s+(0x[0-9a-fA-F]+)\s*(.*)', output, re.IGNORECASE)
    if id_product_match:
        data['idProduct'] = id_product_match.group(1).strip()
        if id_product_match.group(2): data['iProduct_desc'] = id_product_match.group(2).strip()

    # --- String Descriptor Fields (iManufacturer, iProduct, iSerial) ---
    # These rely on lines like: iManufacturer 1 Apricorn
    # Handle cases where the text description might be missing
    imanu_match = re.search(r'iManufacturer\s+\d+\s+(.*)', output)
    if imanu_match: data['iManufacturer'] = imanu_match.group(1).strip()
    iprod_match = re.search(r'iProduct\s+\d+\s+(.*)', output)
    if iprod_match: data['iProduct'] = iprod_match.group(1).strip()
    iserial_match = re.search(r'iSerial\s+\d+\s+(.*)', output)
    if iserial_match: data['iSerial'] = iserial_match.group(1).strip()

    # Use the text descriptions from idVendor/idProduct lines as fallbacks if iManufacturer/iProduct aren't found
    if 'iManufacturer' not in data and 'iManufacturer_desc' in data:
        data['iManufacturer'] = data['iManufacturer_desc']
    if 'iProduct' not in data and 'iProduct_desc' in data:
        data['iProduct'] = data['iProduct_desc']

    # Clean up temporary description fields
    data.pop('iManufacturer_desc', None)
    data.pop('iProduct_desc', None)

    # pprint(data) # Debugging
    return data

# ------------------------------------------------------
# Enumerate "lsusb", filter for Apricorn, gather details
# ------------------------------------------------------
def find_apricorn_device() -> Optional[List[LinuxUsbDeviceInfo]]:
    """
    Enumerates USB devices using 'lsusb', filters for Apricorn devices (VID 0984),
    and gathers detailed information using 'lsusb -v', 'lshw', and 'lsblk'.
    Correlates information based on serial numbers.

    Returns a list of LinuxUsbDeviceInfo objects for detected Apricorn devices.
    Excludes known non-target devices (PID 0221, 0301).
    Returns None if critical commands fail or no devices are found.
    """
    closest_values = {
        # PID: [Product Name Hint, [Sizes in GB]] - Use integers for sizes
        "0310": ["Padlock 3.0", [256, 500, 1000, 2000, 4000, 8000, 16000]],
        "0315": ["Padlock DT", [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000]],
        "0351": ["Aegis Portable", [128, 256, 500, 1000, 2000, 4000, 8000, 12000, 16000]],
        "1400": ["Fortress", [256, 500, 1000, 2000, 4000, 8000, 16000]],
        "1405": ["Padlock SSD", [240, 480, 1000, 2000, 4000]],
        "1406": ["Padlock DT FIPS", [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000]],
        "1407": ["Secure Key 3.0", [16, 30, 60, 120, 240, 480, 1000, 2000, 4000]],
        "1408": ["Fortress L3", [500, 512, 1000, 2000, 4000, 5000, 8000, 16000, 20000]],
        "1409": ["Secure Key 3.0", [16, 32, 64, 128]], # Assume ASK 3NXC (often reports as 1409)
        "1410": ["Secure Key 3Z", [4, 8, 16, 32, 64, 128, 256, 512]],
        "1413": ["Padlock NVX", [500, 1000, 2000]]
    }

    # --- Collect info from system tools ---
    # lshw is generally preferred for matching serial to block device
    lshw_apricorn_info = parse_uasp_info() # List of dicts {'serial': '...', 'logicalname': '/dev/sdx', 'driver': 'uas'/...}
    lsblk_drives = list_usb_drives() # List of dicts {'name': '/dev/sdx', 'serial': '...', 'size_gb': ...}

    # Create lookup maps for easier correlation
    lshw_map = {info['serial']: info for info in lshw_apricorn_info if info.get('serial')}
    lsblk_map = {info['serial']: info for info in lsblk_drives if info.get('serial')}

    # --- Run basic lsusb to find Apricorn VID ---
    lsusb_path = "/usr/bin/lsusb"
    if not os.path.exists(lsusb_path):
        print("Error: 'lsusb' command not found. Cannot list USB devices.", file=sys.stderr)
        return None

    try:
        lsusb_cmd = [lsusb_path]
        result = subprocess.run(lsusb_cmd, capture_output=True, text=True, check=True) # Check for success
    except FileNotFoundError:
         print("Error: 'lsusb' command not found.", file=sys.stderr)
         return None
    except subprocess.CalledProcessError as e:
         print(f"Error running 'lsusb': {e}. Stderr: {e.stderr.strip()}", file=sys.stderr)
         return None
    except Exception as e:
         print(f"Unexpected error running 'lsusb': {e}", file=sys.stderr)
         return None

    # --- Process lsusb output ---
    all_found_devices = []
    processed_serials = set() # Track serials processed to avoid duplicates if lsusb shows multiple lines for same device

    for line in result.stdout.splitlines():
        # Match: Bus 001 Device 002: ID 0984:1408 Apricorn Corp. Fortress L3
        match = re.match(r'Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s+(.*)', line.strip(), re.IGNORECASE)
        if not match:
            continue

        bus_num, dev_num, vid, pid, description = match.groups()
        vid_lower = vid.lower()
        pid_lower = pid.lower()

        # Filter: Apricorn VID, exclude specific PIDs
        if vid_lower != "0984" or pid_lower in ["0221", "0301"]:
            continue

        # --- Get detailed info using lsusb -v ---
        # This dict might be partially populated if lsusb -v fails (e.g., permissions)
        lsusb_v_info = parse_lsusb_output(vid_lower, pid_lower)

        # Extract best available info, prioritizing lsusb -v
        iSerial_str = lsusb_v_info.get("iSerial", "").strip()
        iManufacturer_str = lsusb_v_info.get("iManufacturer", description.split(" ", 1)[0] if description else "Apricorn").strip() # Fallback manufacturer
        iProduct_str = lsusb_v_info.get("iProduct", "").strip() # Get product from lsusb -v if possible
        bcdUSB_str = lsusb_v_info.get("bcdUSB", "0") # Raw string from lsusb -v
        bcdDevice_str = lsusb_v_info.get("bcdDevice", "0x0000") # Raw string from lsusb -v

        # If serial wasn't found via lsusb -v, try to find a match in lshw/lsblk based on PID
        # This is less reliable but a potential fallback
        matched_lshw = None
        matched_lsblk = None

        if not iSerial_str:
             # Attempt to find matching device in lshw based on PID (less reliable)
             # This requires lshw providing product ID info, which it often doesn't reliably
             pass # Skip serial-less devices for now, main matching relies on serial

        # Skip if we've already processed this serial number
        if iSerial_str and iSerial_str in processed_serials:
            continue
        if not iSerial_str:
            # If no serial, we cannot reliably correlate. Log and skip.
            # print(f"Warning: Skipping device VID={vid_lower}, PID={pid_lower} (Bus {bus_num} Dev {dev_num}) - could not determine serial number.", file=sys.stderr)
            continue

        # Mark this serial as processed
        processed_serials.add(iSerial_str)

        # --- Correlate with lshw and lsblk using the serial number ---
        matched_lshw = lshw_map.get(iSerial_str)
        matched_lsblk = lsblk_map.get(iSerial_str)

        # --- Determine Block Device Path ---
        blockDevice_str = "N/A"
        if matched_lshw and matched_lshw.get('logicalname'):
            blockDevice_str = matched_lshw['logicalname']
        elif matched_lsblk and matched_lsblk.get('name'):
            # Fallback to lsblk name if lshw didn't provide it
            blockDevice_str = matched_lsblk['name']
        # else: Remains "N/A"

        # --- Determine UASP Status ---
        SCSIDevice_bool = False # Default to False (not UASP)
        if matched_lshw and matched_lshw.get('driver') == 'uas':
            SCSIDevice_bool = True

        # --- Determine Drive Size ---
        driveSize_val = "N/A" # Use string "N/A" for consistency with Windows OOB
        size_gb_float = 0.0
        if matched_lsblk:
             size_gb_float = matched_lsblk.get('size_gb', 0.0)
        elif matched_lshw:
             # lshw sometimes has size info too, less common than lsblk
             # Check 'size' attribute (usually in bytes)
             size_bytes = matched_lshw.get('size')
             if isinstance(size_bytes, (int, float)):
                 size_gb_float = bytes_to_gb(size_bytes)

        # Find closest standard size if size > 0
        if size_gb_float > 0:
            size_options = closest_values.get(pid_lower, [None, []])[1] # Get size list for PID
            closest_size_int = find_closest(size_gb_float, size_options)
            if closest_size_int is not None:
                driveSize_val = closest_size_int # Store as int if found
            else:
                # If no match found, maybe report raw GB? Or stick to N/A?
                # Stick to N/A if lookup fails, indicates unusual size or missing PID in map
                driveSize_val = "N/A" # Fallback if closest match fails
        # If size_gb_float is 0 or less, it remains "N/A"

        # --- Refine Product Name ---
        # Use lsusb -v product name first, fallback to lshw product, then description hint
        if not iProduct_str and matched_lshw:
             iProduct_str = matched_lshw.get('product', '').strip()
        if not iProduct_str:
             # Use the hint from our closest_values map
             iProduct_str = closest_values.get(pid_lower, ["Unknown Product", []])[0]

        # --- Parse USB/Device Versions ---
        bcdUSB_float = parse_usb_version(bcdUSB_str)
        # Clean bcdDevice string (remove 0x, ensure 4 hex digits if possible)
        bcdDevice_clean = bcdDevice_str.lower().replace('0x', '').replace('.', '')
        bcdDevice_formatted = f"0x{bcdDevice_clean.zfill(4)}" # Pad with zeros if needed


        # --- Create Device Info Object ---
        dev_info = LinuxUsbDeviceInfo(
            bcdUSB=bcdUSB_float,
            idVendor=vid_lower,
            idProduct=pid_lower,
            bcdDevice=bcdDevice_formatted,
            iManufacturer=iManufacturer_str,
            iProduct=iProduct_str,
            iSerial=iSerial_str,
            SCSIDevice=SCSIDevice_bool,
            driveSizeGB=driveSize_val, # Can be int or "N/A"
            blockDevice=blockDevice_str
        )
        all_found_devices.append(dev_info)

    return all_found_devices if all_found_devices else None

# ---------------
# Example Usage
# ---------------
def main(find_apricorn_device_func):
    """
    Main function to find and display information about connected Apricorn devices.

    Args:
        find_apricorn_device_func (callable): The function to call to get devices.
    """
    # Note: This script needs permissions (sudo) for some commands (lshw, fdisk, lsusb -v)
    # Check if running as root, warn if not
    if os.geteuid() != 0:
        print("Warning: This script may require root privileges (sudo) for full functionality (lshw, fdisk, lsusb -v).", file=sys.stderr)
        print("Attempting to run with current privileges...", file=sys.stderr)

    devices = find_apricorn_device_func()
    if not devices:
        print("\nNo Apricorn devices found.")
    else:
        print(f"\nFound {len(devices)} Apricorn device(s):")
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            # Use vars() to dynamically access attributes from the dataclass instance
            attributes = vars(dev)
            for field_name, value in attributes.items():
                print(f"  {field_name}: {value}")
        print() # Add a final newline for clarity

if __name__ == "__main__":
    main(find_apricorn_device)
