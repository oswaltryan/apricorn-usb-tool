#!/usr/bin/env python3

import subprocess
import re
from typing import List, Optional, Dict, Any
import json
import os
import sys

from .common import UsbDeviceInfo, populate_device_version
from .device_config import closest_values
from .utils import bytes_to_gb, find_closest


def _sg_path_for_block(block_device: str) -> Optional[str]:
    """Derive /dev/sgX corresponding to a block device like /dev/sdX.

    Uses sysfs: /sys/class/block/<name>/device/scsi_generic/* -> sgN.
    Returns the absolute /dev/sgN path or None if not resolvable.
    """
    try:
        if not (isinstance(block_device, str) and block_device.startswith("/dev/")):
            return None
        name = os.path.basename(block_device)
        # Common sysfs locations
        cand_dirs = [
            f"/sys/class/block/{name}/device/scsi_generic",
            f"/sys/block/{name}/device/scsi_generic",
        ]
        for d in cand_dirs:
            if os.path.isdir(d):
                try:
                    entries = [e for e in os.listdir(d) if e.startswith("sg")]
                except Exception:
                    entries = []
                if entries:
                    return f"/dev/{entries[0]}"
        return None
    except Exception:
        return None


def sort_devices(devices: list) -> list:
    """Sort devices by block device path.

    Args:
        devices: List of ``UsbDeviceInfo`` instances.

    Returns:
        Devices ordered alphabetically by the ``blockDevice`` attribute with
        unknown paths placed at the end.
    """
    if not devices:
        return []

    def _key(dev):
        block_dev = getattr(dev, "blockDevice", "")
        return (
            block_dev
            if isinstance(block_dev, str) and block_dev.startswith("/dev/")
            else "~~~~~"
        )

    return sorted(devices, key=_key)


def parse_lsblk_size(size_str: str) -> float:
    """
    Parse a size string from the 'lsblk' command output (e.g., '465.8G', '14.2T', '500M')
    and return the size in gigabytes as a float. Returns 0.0 if the string is unparsable.
    """
    if not size_str:
        return 0.0
    size_str = size_str.strip().upper()
    # More robust regex to handle potential commas or other chars
    match = re.match(r"([\d\.,]+)\s*([GMTEK])?", size_str)
    if not match:
        return 0.0

    numeric_part, unit = match.groups()
    # Clean up numeric part (remove commas)
    numeric_part = numeric_part.replace(",", "")

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
        # Assume bytes if no unit or unrecognized unit
        return bytes_to_gb(val)


# -----------------------------------------------------------
# Gather block device info: name, serial, size (converted to GB)
# -----------------------------------------------------------
def list_usb_drives():
    """
    Lists USB drives using the 'lsblk' command and extracts their serial number,
    size, and device name.
    Returns a list of dictionaries, where each dictionary contains 'name' (str, e.g., /dev/sda),
    'serial' (string), and 'size_gb' (float).
    Filters for likely valid serials (e.g., 12 chars) but relies on later correlation.
    Handles potential errors during subprocess execution.
    """
    # -p includes full path /dev/..., -l provides list format
    # -e 7 excludes loop devices (common snaps/etc)
    cmd = ["lsblk", "-p", "-o", "NAME,SERIAL,SIZE", "-d", "-n", "-l", "-e", "7"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=10
        )  # Don't check return code here
        if result.returncode != 0:
            print(
                f"Warning: 'lsblk' command failed with code {result.returncode}. Stderr: {result.stderr.strip()}",
                file=sys.stderr,
            )
            # Don't return empty if stderr indicates permission issues but stdout has data (common in containers)
            if not result.stdout.strip() and "Permission denied" not in result.stderr:
                return []
        if not result.stdout.strip():
            # print("Warning: 'lsblk' command returned no output.", file=sys.stderr)
            return []  # Handle case where lsblk runs but finds nothing
    except FileNotFoundError:
        print(
            "Error: 'lsblk' command not found. Cannot determine drive sizes or paths.",
            file=sys.stderr,
        )
        return []
    except subprocess.TimeoutExpired:
        print("Warning: 'lsblk' command timed out.", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error running 'lsblk': {e}", file=sys.stderr)
        return []

    drives_info = []
    processed_serials = (
        set()
    )  # Avoid duplicates if lsblk lists partitions with same serial
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Expecting NAME SERIAL SIZE format
        parts = line.split(None, 3)
        if len(parts) < 4:
            # print(f"Warning: Skipping malformed lsblk line: '{line}'") # Debugging
            continue

        name, serial, size_str, rm_flag = parts
        # Check if serial looks potentially valid (not None, not '-', reasonable length maybe?)
        # Rely more on matching via lshw/lsusb later.
        if not serial or serial == "-":
            continue

        # Basic check to avoid processing partition entries if main device was already added
        if serial in processed_serials:
            continue

        media_type = "Unknown"
        if rm_flag == "1":
            media_type = "Removable Media"
        elif rm_flag == "0":
            media_type = "Basic Disk"

        size_gb = parse_lsblk_size(size_str)
        drives_info.append(
            {
                "name": name,  # Full path like /dev/sda
                "serial": serial,
                "size_gb": size_gb,
                "mediaType": media_type,
            }
        )
        processed_serials.add(serial)  # Mark serial as seen

    # print("lsblk Results (Filtered):")
    # pprint(drives_info)
    # print()
    return drives_info


def parse_uasp_info() -> Dict[str, Dict[str, Optional[str]]]:
    import shutil  # Moved import here as it's only used here and in fdisk

    lshw_path = shutil.which("lshw")
    if not lshw_path:
        if os.path.exists("/usr/bin/lshw"):  # Common fallback path
            lshw_path = "/usr/bin/lshw"
        else:
            print(
                "Error: 'lshw' command not found. Cannot get detailed hardware info.",
                file=sys.stderr,
            )
            return {}

    sudo_path = shutil.which("sudo")
    if not sudo_path:
        # Try common fallback for sudo if not in PATH (less likely for sudo but good to check)
        if os.path.exists("/usr/bin/sudo"):
            sudo_path = "/usr/bin/sudo"
        else:
            print("Error: 'sudo' command not found. Cannot run lshw.", file=sys.stderr)
            return {}

    cmd = [sudo_path, lshw_path, "-class", "disk", "-class", "storage", "-json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=20
        )
        # print(result.stdout) # Keep for debugging if needed, but remove for final
    except subprocess.TimeoutExpired:
        print(f"Warning: '{' '.join(cmd)}' timed out.", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"Error running '{' '.join(cmd)}': {e}", file=sys.stderr)
        return {}

    if result.returncode != 0:
        if (
            "must be root" in result.stderr.lower()
            or "permission denied" in result.stderr.lower()
        ):
            print(
                f"Warning: Permission error running '{' '.join(cmd)}'. Check sudo setup. Detailed hardware info may be incomplete.",
                file=sys.stderr,
            )
            if not result.stdout.strip():
                return {}
        else:
            print(
                f"Warning: '{' '.join(cmd)}' failed (code {result.returncode}). Stderr: {result.stderr.strip()}",
                file=sys.stderr,
            )
            if not result.stdout.strip():
                return {}

    if not result.stdout.strip():
        return {}

    try:
        raw_data = json.loads(result.stdout)
        if isinstance(raw_data, dict):
            all_devices_from_lshw = [raw_data]
        elif isinstance(raw_data, list):
            all_devices_from_lshw = raw_data
        else:
            print(
                "Warning: Unexpected JSON format from 'lshw' (expected list or dict).",
                file=sys.stderr,
            )
            return {}
    except json.JSONDecodeError:
        print(
            "Error: Failed to parse JSON output from 'lshw'. Output was:",
            file=sys.stderr,
        )
        print(result.stdout[:500] + "...", file=sys.stderr)
        return {}

    # Helper function to normalize lshw values that can be str or list
    def _normalize_lshw_value(value: Any) -> Optional[str]:
        if isinstance(value, list) and value:
            # If it's a list, take the first element and convert to string
            return str(value[0])
        if isinstance(value, str):
            return value
        return None

    # This will be the final map returned by the function
    lshw_data_by_name: Dict[str, Dict[str, Optional[str]]] = {}

    # Temporary storage during parsing
    # Keyed by device path (e.g., /dev/sda)
    temp_disk_node_info: Dict[str, Dict[str, Optional[str]]] = {}
    # Keyed by serial number
    temp_controller_node_info: Dict[str, Dict[str, Optional[str]]] = {}

    # Inner helper to find /dev/sdX or /dev/nvmeXnY (as it was)
    def find_dev_path(logicalname: Any) -> Optional[str]:
        if isinstance(logicalname, str):
            if (
                logicalname.startswith("/dev/sd")
                and len(logicalname) > len("/dev/sd")
                and logicalname[-1].isalpha()
            ):
                return logicalname
            if (
                logicalname.startswith("/dev/nvme")
                and len(logicalname) > len("/dev/nvme")
                and logicalname[-1].isdigit()
            ):
                return logicalname
        elif isinstance(logicalname, list):
            for item in logicalname:
                path = find_dev_path(item)
                if path:
                    return path
        return None

    # Recursive function to collect information from lshw nodes
    def collect_lshw_info_recursive(device_node: Dict[str, Any]):
        nonlocal temp_disk_node_info, temp_controller_node_info  # Ensure modification of outer scope maps
        if not isinstance(device_node, dict):
            return

        # Extract common fields from the current node
        node_logicalname = device_node.get("logicalname")  # Keep raw for find_dev_path
        node_serial = _normalize_lshw_value(device_node.get("serial"))
        node_driver = _normalize_lshw_value(
            device_node.get("configuration", {}).get("driver")
        )
        node_product = _normalize_lshw_value(device_node.get("product"))
        node_vendor = _normalize_lshw_value(device_node.get("vendor"))

        # Attempt to find a block device path (/dev/sdX, /dev/nvmeXnY)
        dev_path = find_dev_path(node_logicalname)

        # If it's a disk node with a recognized path, store its info
        if dev_path:
            if dev_path not in temp_disk_node_info:  # Store if new
                temp_disk_node_info[dev_path] = {
                    "serial": node_serial,
                    "product": node_product,
                    "vendor": node_vendor,
                    "driver": None,  # Driver to be filled by correlation later
                }
            else:  # If already exists, update missing fields
                entry = temp_disk_node_info[dev_path]
                if node_serial and not entry.get("serial"):
                    entry["serial"] = node_serial
                if node_product and not entry.get("product"):
                    entry["product"] = node_product
                if node_vendor and not entry.get("vendor"):
                    entry["vendor"] = node_vendor

        # If it's a storage controller with a relevant driver ('uas' or 'usb-storage') and serial
        if node_serial and node_driver and node_driver in ("uas", "usb-storage"):
            should_update_controller = False
            if node_serial not in temp_controller_node_info:
                should_update_controller = True
            else:
                existing_controller_driver = temp_controller_node_info[node_serial].get(
                    "driver"
                )
                if not existing_controller_driver:  # No driver stored yet
                    should_update_controller = True
                elif (
                    existing_controller_driver == "usb-storage" and node_driver == "uas"
                ):  # Prefer 'uas'
                    should_update_controller = True

            if should_update_controller:
                temp_controller_node_info[node_serial] = {
                    "driver": node_driver,
                    "product": node_product,  # Store controller's product/vendor too
                    "vendor": node_vendor,
                }

        # Recursively process children
        children = device_node.get("children")
        if isinstance(children, list):
            for child_node in children:
                collect_lshw_info_recursive(child_node)

    # --- Pass 1: Collect information by recursively processing all devices ---
    for top_level_dev_node in all_devices_from_lshw:
        collect_lshw_info_recursive(top_level_dev_node)

    # --- Pass 2: Correlate and build the final lshw_data_by_name map ---
    for path, disk_data in temp_disk_node_info.items():
        final_entry = {
            "serial": disk_data.get("serial"),
            "product": disk_data.get("product"),
            "vendor": disk_data.get("vendor"),
            "driver": None,  # Initialize driver to None
        }

        disk_serial_num = disk_data.get("serial")
        if disk_serial_num and disk_serial_num in temp_controller_node_info:
            controller_data = temp_controller_node_info[disk_serial_num]
            final_entry["driver"] = controller_data.get(
                "driver"
            )  # Assign driver from controller

            # Use controller's product/vendor as fallback if disk node's info was missing
            if not final_entry.get("product") and controller_data.get("product"):
                final_entry["product"] = controller_data.get("product")
            if not final_entry.get("vendor") and controller_data.get("vendor"):
                final_entry["vendor"] = controller_data.get("vendor")

        lshw_data_by_name[path] = final_entry

    return lshw_data_by_name


# -----------------------------
# Parse "lsusb -v -d <vid:pid>"
# -----------------------------
def parse_lsusb_output(
    vid: str, pid: str
) -> List[Dict[str, str]]:  # Return a LIST of dicts
    """
    Runs 'lsusb -v -d vid:pid' (may require permissions) and parses output
    for USB descriptor details FOR ALL MATCHING DEVICES.

    Returns a LIST of dictionaries, where each dictionary contains keys like
    'bcdUSB', 'idVendor', 'idProduct', 'bcdDevice', 'iManufacturer', 'iProduct', 'iSerial'
    for each distinct device found matching the VID:PID. Returns empty list on failure or no devices.
    """
    import shutil  # Ensure shutil is available

    lsusb_path = shutil.which("lsusb")
    if not lsusb_path:
        # Try common fallback
        if os.path.exists("/usr/bin/lsusb"):
            lsusb_path = "/usr/bin/lsusb"
        else:
            return []  # Return empty list

    # Use sudo if available and needed (heuristic: check if we are not root)
    sudo_prefix = []
    geteuid = getattr(os, "geteuid", None)
    if geteuid and geteuid() != 0:
        sudo_path = shutil.which("sudo")
        if sudo_path:
            sudo_prefix = [sudo_path]

    cmd = sudo_prefix + [lsusb_path, "-v", "-d", f"{vid}:{pid}"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=15
        )  # Increased timeout slightly
    except subprocess.TimeoutExpired:
        print(f"Warning: '{' '.join(cmd)}' timed out.", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error running '{' '.join(cmd)}': {e}", file=sys.stderr)
        return []

    # Handle errors but proceed if there's output
    if result.returncode != 0:
        stderr_lower = result.stderr.lower()
        if "could not open" in stderr_lower or "permission denied" in stderr_lower:
            # Fail silently if permissions likely cause and no output
            if not result.stdout.strip():
                return []
        elif "not found" in stderr_lower:
            # Device might have disconnected
            if not result.stdout.strip():
                return []
        else:
            print(
                f"Warning: '{' '.join(cmd)}' failed (code {result.returncode}). Stderr: {result.stderr.strip()}",
                file=sys.stderr,
            )
            if not result.stdout.strip():
                return []  # Return empty only if no output at all

    output = result.stdout
    devices_found = []

    # Simpler Approach: Find all Device Descriptors and parse data relative to them
    device_descriptor_matches = list(re.finditer(r"Device Descriptor:", output))

    if not device_descriptor_matches:
        return []

    for i, match_obj in enumerate(device_descriptor_matches):
        start_pos = match_obj.start()
        # Determine end position: start of next descriptor or end of string
        end_pos = (
            device_descriptor_matches[i + 1].start()
            if i + 1 < len(device_descriptor_matches)
            else len(output)
        )
        device_output = output[start_pos:end_pos]

        # Now parse this specific device_output section
        data = {}
        # Use regex with re.IGNORECASE | re.MULTILINE

        # --- Standard Descriptor Fields ---
        bcd_match = re.search(
            r"bcdUSB\s+([\d\.xXa-fA-F]+)", device_output, re.IGNORECASE
        )
        if bcd_match:
            data["bcdUSB"] = bcd_match.group(1).strip()

        bcd_dev_match = re.search(
            r"bcdDevice\s+([\d\.xXa-fA-F]+)", device_output, re.IGNORECASE
        )
        if bcd_dev_match:
            data["bcdDevice"] = bcd_dev_match.group(1).strip()

        # idVendor and idProduct - we already know these from the input vid/pid
        data["idVendor"] = (
            f"{vid}"  # Store consistently without 0x ? Let's keep vid/pid as passed
        )
        data["idProduct"] = f"{pid}"
        # Try to find text descriptions associated with them within this device's section
        id_vendor_match = re.search(
            r"idVendor\s+0x" + vid + r"\s+(.*)", device_output, re.IGNORECASE
        )
        if id_vendor_match and id_vendor_match.group(1).strip():
            data["iManufacturer_desc"] = id_vendor_match.group(1).strip()
        id_product_match = re.search(
            r"idProduct\s+0x" + pid + r"\s+(.*)", device_output, re.IGNORECASE
        )
        if id_product_match and id_product_match.group(1).strip():
            data["iProduct_desc"] = id_product_match.group(1).strip()

        # --- String Descriptor Fields (iManufacturer, iProduct, iSerial) ---
        # Use re.MULTILINE here
        imanu_match = re.search(
            r"^\s*iManufacturer\s+\d+\s+(.+)$",
            device_output,
            re.MULTILINE | re.IGNORECASE,
        )
        if imanu_match and imanu_match.group(1).strip():
            data["iManufacturer"] = imanu_match.group(1).strip()

        iprod_match = re.search(
            r"^\s*iProduct\s+\d+\s+(.+)$", device_output, re.MULTILINE | re.IGNORECASE
        )
        if iprod_match and iprod_match.group(1).strip():
            data["iProduct"] = iprod_match.group(1).strip()

        iserial_match = re.search(
            r"^\s*iSerial\s+\d+\s+([^\s]+(?: [^\s]+)*)$",
            device_output,
            re.MULTILINE | re.IGNORECASE,
        )  # Allow spaces in serial? No, lsusb doesn't usually show them. Use original regex.
        iserial_match = re.search(
            r"^\s*iSerial\s+\d+\s+([^\s]+)$",
            device_output,
            re.MULTILINE | re.IGNORECASE,
        )  # Original
        if iserial_match and iserial_match.group(1).strip():
            data["iSerial"] = iserial_match.group(1).strip()

        # --- Fallbacks and Cleanup ---
        if "iManufacturer" not in data and data.get("iManufacturer_desc"):
            data["iManufacturer"] = data["iManufacturer_desc"]
        if "iProduct" not in data and data.get("iProduct_desc"):
            data["iProduct"] = data["iProduct_desc"]

        data.pop("iManufacturer_desc", None)
        data.pop("iProduct_desc", None)

        # Only add if we found the essential serial number for correlation
        if data.get("iSerial"):
            devices_found.append(data)

    return devices_found


# ------------------------------------------------------
# Enumerate "lsusb", filter for Apricorn, gather details - MODIFIED
# ------------------------------------------------------
def find_apricorn_device() -> List[UsbDeviceInfo]:  # Return List, never None
    """
    Enumerates USB devices using 'lsusb', filters for Apricorn devices (VID 0984),
    and gathers detailed information using 'lsusb -v', 'lshw', and 'lsblk'.
    Correlates information primarily based on block device name, using serial
    number as the link to lsusb data. Handles multiple devices sharing VID:PID.

    Returns a list of UsbDeviceInfo objects for detected Apricorn devices.
    Excludes known non-target devices (PID 0221, 0301).
    Returns an empty list if no devices are found or critical commands fail.
    """
    import shutil  # Ensure shutil is available

    # --- Collect info from system tools ---
    lshw_data_map_by_name = parse_uasp_info()  # Returns Dict[name, {info}]
    lsblk_drives = list_usb_drives()  # Returns List[Dict]

    # CHANGE: Create lookup map for lsblk based on name (block path)
    lsblk_map_by_name = {
        info["name"]: info for info in lsblk_drives if info.get("name")
    }

    # --- Run basic lsusb to find Apricorn VID ---
    lsusb_path = shutil.which("lsusb")
    if not lsusb_path:
        # Try common fallback
        if os.path.exists("/usr/bin/lsusb"):
            lsusb_path = "/usr/bin/lsusb"
        else:
            print(
                "Error: 'lsusb' command not found. Cannot list USB devices.",
                file=sys.stderr,
            )
            return []  # Return empty list

    try:
        lsusb_cmd = [lsusb_path]
        result = subprocess.run(lsusb_cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print(
            "Error: 'lsusb' command not found (should have been caught earlier).",
            file=sys.stderr,
        )
        return []
    except subprocess.CalledProcessError as e:
        print(
            f"Error running 'lsusb': {e}. Stderr: {e.stderr.strip()}", file=sys.stderr
        )
        return []
    except Exception as e:
        print(f"Unexpected error running 'lsusb': {e}", file=sys.stderr)
        return []

    # --- Process lsusb output to find Apricorn VID:PIDs and get detailed lsusb -v data ---
    all_found_devices = []
    processed_vid_pid = set()
    # CHANGE: Store lsusb -v results mapped by serial number for later lookup
    lsusb_details_map_by_serial: Dict[str, Dict[str, str]] = {}

    for line in result.stdout.splitlines():
        match = re.match(
            r"Bus\s+\d+\s+Device\s+\d+:\s+ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)",
            line.strip(),
            re.IGNORECASE,
        )
        if not match:
            continue

        vid, pid = match.groups()
        vid_lower = vid.lower()
        pid_lower = pid.lower()

        if vid_lower != "0984" or pid_lower in ["0221", "0301"]:
            continue

        if (vid_lower, pid_lower) in processed_vid_pid:
            continue
        processed_vid_pid.add((vid_lower, pid_lower))

        lsusb_v_results = parse_lsusb_output(vid_lower, pid_lower)  # Returns a list

        if not lsusb_v_results:
            print(
                f"  Warning: 'lsusb -v' yielded no parsable device details for {vid_lower}:{pid_lower}."
            )
            continue

        # Populate the map keyed by serial
        for device_details in lsusb_v_results:
            iSerial = device_details.get("iSerial")
            if (
                iSerial and iSerial not in lsusb_details_map_by_serial
            ):  # Avoid overwriting if serial conflict (unlikely but possible)
                lsusb_details_map_by_serial[iSerial] = device_details
            elif iSerial:
                print(
                    f"  Warning: Duplicate serial '{iSerial}' found in lsusb -v results for different devices/VID:PIDs. Using first entry."
                )

    processed_block_devices = (
        set()
    )  # Avoid processing the same block device multiple times if listed differently

    for block_path, lsblk_info in lsblk_map_by_name.items():
        if block_path in processed_block_devices:
            continue

        # --- Get Serial from lsblk/lshw for this block device ---
        serial_str = lsblk_info.get("serial")
        matched_lshw_data = lshw_data_map_by_name.get(block_path)  # Look up by path

        # Use lshw serial if lsblk serial is missing or '-', prefer lshw if both exist? Let's prefer lshw if available.
        if matched_lshw_data and matched_lshw_data.get("serial"):
            serial_str = matched_lshw_data["serial"]

        if not serial_str:
            processed_block_devices.add(block_path)
            continue  # Cannot correlate without serial

        # --- Find corresponding lsusb -v details using the serial ---
        lsusb_v_info = lsusb_details_map_by_serial.get(serial_str)

        if not lsusb_v_info:
            processed_block_devices.add(block_path)
            continue  # Cannot proceed without lsusb info for VID/PID etc.

        # Mark this device as processed (using both path and serial to be safe)
        processed_block_devices.add(block_path)

        # --- Extract Primary Information (Prioritize lsusb -v) ---
        # Get VID/PID from lsusb data; re-check filter in case lsusb -v matched a filtered PID via serial
        vid_lower = lsusb_v_info.get("idVendor", "").lower()
        pid_lower = lsusb_v_info.get("idProduct", "").lower()
        if vid_lower != "0984" or pid_lower in ["0221", "0301"]:
            print(
                f"  Info: Skipping {block_path} (Serial: {serial_str}) as its lsusb data indicates excluded VID/PID {vid_lower}:{pid_lower}."
            )
            continue

        iManufacturer_str = lsusb_v_info.get("iManufacturer", "").strip()
        iProduct_str = lsusb_v_info.get("iProduct", "").strip()
        bcdUSB_str = lsusb_v_info.get("bcdUSB", "0")
        try:
            bcdUSB_float = float(bcdUSB_str)
        except (ValueError, TypeError):
            bcdUSB_float = 0.0
        bcdDevice_str = lsusb_v_info.get("bcdDevice", "0x0000")
        cleaned_bcdDevice_str = (
            bcdDevice_str.lower().replace("0x", "").replace(".", "").zfill(4)
        )

        # --- Determine Block Device Path (we already have it) ---
        blockDevice_str = block_path  # This is our primary key now

        # --- Determine UASP Status (from lshw data) ---
        SCSIDevice_bool = False
        driver: Optional[str] = "N/A"
        if matched_lshw_data:
            driver = matched_lshw_data.get("driver")
            if driver == "uas":
                SCSIDevice_bool = True

        # --- Determine Drive Size (from lsblk data) ---
        driveSize_val: Any = "N/A (OOB Mode)"
        size_gb_float = lsblk_info.get("size_gb", 0.0)

        # Find closest standard size if size > 0
        if size_gb_float > 0:
            pid_for_lookup = pid_lower
            size_options_pid = closest_values.get(pid_for_lookup, (None, []))[1]
            size_options_bcd = closest_values.get(cleaned_bcdDevice_str, (None, []))[1]
            size_options = size_options_pid
            lookup_key = pid_for_lookup
            if not size_options and size_options_bcd:
                size_options = size_options_bcd
                lookup_key = cleaned_bcdDevice_str
            elif not size_options and not size_options_bcd:
                driveSize_val = round(size_gb_float)

            if size_options:
                closest_size_int = find_closest(size_gb_float, size_options)
                if closest_size_int is not None:
                    driveSize_val = closest_size_int
                else:
                    driveSize_val = round(size_gb_float)
                    print(
                        f"    Reporting Raw Size: {driveSize_val} GB (No standard match found for key '{lookup_key}')"
                    )
        else:  # If lsblk had size 0 or missing
            driveSize_val = "N/A (OOB Mode)"

        mediaType_str = lsblk_info.get("mediaType", "Unknown")

        # --- Refine Product & Manufacturer Name (using fallbacks) ---
        if not iProduct_str and matched_lshw_data:
            lshw_product_val = matched_lshw_data.get("product")
            if lshw_product_val:
                if lshw_product_val:
                    lshw_product = lshw_product_val.strip()
                    processed_product = ""
                    if isinstance(lshw_product_val, list) and lshw_product_val:
                        processed_product = str(lshw_product_val[0])
                    elif isinstance(lshw_product_val, str):
                        processed_product = lshw_product_val
                    lshw_product = processed_product.strip()
                    if lshw_product:
                        iProduct_str = lshw_product
        if not iProduct_str:
            pid_for_lookup = pid_lower
            product_hint_pid: Optional[str] = closest_values.get(
                pid_for_lookup, (None, [])
            )[0]
            product_hint_bcd: Optional[str] = closest_values.get(
                cleaned_bcdDevice_str, (None, [])
            )[0]
            if product_hint_pid:
                iProduct_str = product_hint_pid
            elif product_hint_bcd:
                iProduct_str = product_hint_bcd
            else:
                iProduct_str = f"Unknown Product ({pid_lower}/{cleaned_bcdDevice_str})"

        if not iManufacturer_str and matched_lshw_data:
            lshw_vendor_val = matched_lshw_data.get("vendor")
            vendor_name = ""
            if isinstance(lshw_vendor_val, list) and lshw_vendor_val:
                vendor_name = str(lshw_vendor_val[0]).strip()
            elif isinstance(lshw_vendor_val, str):
                vendor_name = lshw_vendor_val.strip()
            if vendor_name:
                iManufacturer_str = vendor_name
        if not iManufacturer_str:
            iManufacturer_str = "Apricorn"

        # --- Final Type Coercion ---
        if isinstance(iProduct_str, list):
            iProduct_str = str(iProduct_str[0]) if iProduct_str else "Unknown Product"
        if not isinstance(iProduct_str, str):
            iProduct_str = str(iProduct_str)

        if isinstance(iManufacturer_str, list):
            iManufacturer_str = (
                str(iManufacturer_str[0])
                if iManufacturer_str
                else "Unknown Manufacturer"
            )
        if not isinstance(iManufacturer_str, str):
            iManufacturer_str = str(iManufacturer_str)

        version_info = {}
        if isinstance(blockDevice_str, str):
            sg_path = _sg_path_for_block(blockDevice_str)
            if sg_path:
                version_info = populate_device_version(sg_path)

        dev_info = UsbDeviceInfo(
            bcdUSB=bcdUSB_float,
            idVendor=vid_lower,
            idProduct=pid_lower,
            bcdDevice=cleaned_bcdDevice_str,
            iManufacturer=iManufacturer_str,
            iProduct=iProduct_str,
            iSerial=serial_str,
            SCSIDevice=SCSIDevice_bool,
            driveSizeGB=driveSize_val,
            mediaType=mediaType_str,
            **version_info,
        )

        if getattr(dev_info, "scbPartNumber", "N/A") == "N/A":
            for _k in (
                "scbPartNumber",
                "hardwareVersion",
                "modelID",
                "mcuFW",
                "bridgeFW",
            ):
                try:
                    delattr(dev_info, _k)
                except AttributeError:
                    pass

        setattr(dev_info, "blockDevice", blockDevice_str)

        all_found_devices.append(dev_info)

    # --- Final Check for Duplicates based on Serial ---
    final_devices_by_serial = {}
    for dev in all_found_devices:
        if dev.iSerial not in final_devices_by_serial:
            final_devices_by_serial[dev.iSerial] = dev
        else:
            print(
                f"Warning: Multiple entries found for serial {dev.iSerial}. Keeping the first one found."
            )

    return list(final_devices_by_serial.values())


# ---------------
# Example Usage
# ---------------
def main(find_apricorn_device_func=None):
    """
    Main function to find and display information about connected Apricorn devices.

    Args:
        find_apricorn_device_func (callable): The function to call to get devices.
    """
    import shutil  # Import here for fdisk/lshw/lsusb path finding

    geteuid = getattr(os, "geteuid", None)
    if geteuid and geteuid() != 0:
        print(
            "Warning: This script may require root privileges (sudo) for full functionality (lshw, fdisk, lsusb -v).",
            file=sys.stderr,
        )
        if not shutil.which("sudo"):
            print(
                "Warning: 'sudo' command not found. Root access may be required manually.",
                file=sys.stderr,
            )
        print("Attempting to run with current privileges...", file=sys.stderr)
        print("-" * 30, file=sys.stderr)

    finder = (
        find_apricorn_device
        if find_apricorn_device_func is None
        else find_apricorn_device_func
    )
    devices = finder()  # Should now return a list
    if not devices:
        print("\nNo Apricorn devices found or failed to gather sufficient info.")
    else:
        print(f"Found {len(devices)} Apricorn device(s):")
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            attributes = dict(vars(dev))
            attributes.pop("bridgeFW", None)
            for field_name, value in attributes.items():
                print(f"  {field_name:<15}: {value}")
        print()


if __name__ == "__main__":
    main(find_apricorn_device)
