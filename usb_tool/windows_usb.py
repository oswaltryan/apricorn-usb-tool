import libusb as usb
import ctypes as ct
from dataclasses import dataclass
import json
from pprint import pprint
import subprocess
import win32com.client

# Configure libusb to use the included libusb-1.0.dll
usb.config(LIBUSB=None)

# ==================================
# Helper Functions
# ==================================

def bytes_to_gb(bytes_value):
    """Convert bytes to gigabytes."""
    return bytes_value / (1024 ** 3)

def find_closest(target, options):
    """Find the closest value in 'options' to 'target'."""
    closest = min(options, key=lambda x: abs(x - target))
    return int(closest)

def parse_usb_version(bcd):
    """Convert a BCD USB version to a human-readable string (e.g., '2.0', '3.1')."""
    major = (bcd & 0xFF00) >> 8
    minor = (bcd & 0x00F0) >> 4
    subminor = bcd & 0x000F
    if subminor:
        return f"{major}.{minor}{subminor}"
    return f"{major}.{minor}"

def read_string_descriptor_ascii(handle, index):
    """Read a string descriptor from a USB device and return it as ASCII."""
    if index == 0:
        return ""
    buf = (ct.c_ubyte * 256)()
    rc = usb.get_string_descriptor_ascii(handle, index, buf, ct.sizeof(buf))
    if rc < 0:
        return ""
    return bytes(buf[:rc]).decode("utf-8", errors="replace")

def get_all_usb_controller_names():
    """
    Retrieve information for Apricorn devices (VID '0984') on the system.
    Returns a list of dictionaries, each containing keys 'DeviceID' and 'ControllerName'.
    """
    ps_script = r'''
    Get-CimInstance Win32_USBControllerDevice | ForEach-Object {
        $controller = Get-CimInstance -CimInstance $_.Antecedent
        $device = Get-CimInstance -CimInstance $_.Dependent
        if ($device.DeviceID -like "*VID_0984*") {
            [PSCustomObject]@{
                DeviceID = $device.DeviceID
                ControllerName = $controller.Name
            }
        }
    } | ConvertTo-Json
    '''
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"PowerShell error: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)

        # In case a single object was returned, wrap it in a list
        if isinstance(data, dict):
            data = [data]

        # Convert to a list of dictionaries, normalizing DeviceID to uppercase
        usb_controllers = [
            {
                'DeviceID': item['DeviceID'].upper(),
                'ControllerName': item['ControllerName'][:5] if item['ControllerName'].startswith('Intel') else 'ASMedia'
            }
            for item in data
        ]

        # print("USB Controllers:")
        # pprint(usb_controllers)
        # print()
        return usb_controllers

    except json.JSONDecodeError:
        # print("Failed to parse PowerShell output")
        return []


# ==================================
# Dataclasses and Custom Errors
# ==================================

class UsbTreeError(Exception):
    """Custom exception for USB tree errors."""
    pass

@dataclass
class WinUsbDeviceInfo:
    """
    Dataclass representing a USB device information structure.
    Includes busNumber and deviceAddress to differentiate devices.
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
    usbController: str = ""
    busNumber: int = 0
    deviceAddress: int = 0

# ==================================
# Gathering Apricorn Device Info
# ==================================

locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
service = locator.ConnectServer(".", "root\\cimv2")

def get_wmi_usb_devices():
    """
    Fetch all USB devices from WMI (Win32_PnPEntity) whose DeviceID starts with 'USB\\VID_'.
    Returns a list of dicts with relevant info (VID, PID, manufacturer, description, serial).
    """
    query = "SELECT * FROM Win32_PnPEntity WHERE DeviceID LIKE 'USB%'"
    usb_devices = service.ExecQuery(query)

    devices_info = []
    for device in usb_devices:
        device_id = device.DeviceID
        if not device_id.upper().startswith("USB\\VID_") or "0984" not in device_id:
            continue

        parts = device_id.split("\\", 2)
        if len(parts) < 2:
            continue

        vid_pid = parts[1].split("&")
        vid = vid_pid[0].replace('VID_', '').lower()
        pid = vid_pid[1].replace('PID_', '').lower()
        serial = parts[2] if len(parts) > 2 else ""

        devices_info.append({
            "vid": vid,
            "pid": pid,
            "manufacturer": "Apricorn",
            "description": device.Description or "",
            "serial": serial
        })

    # print("wmi_usb_devices:")
    # pprint(devices_info)
    # print()
    return devices_info

def get_wmi_usb_drives():
    """
    Fetch all USB drives from WMI (Win32_DiskDrive WHERE InterfaceType='USB').
    Returns a list of dicts with caption, size in GB, closest_match, iProduct, pnpdeviceid, etc.
    """
    query = """
SELECT * FROM Win32_DiskDrive
WHERE InterfaceType='USB'
   OR InterfaceType='SCSI'
"""
    usb_drives = service.ExecQuery(query)
    drives_info = []
    
    for drive in usb_drives:
        if "Apricorn" in getattr(drive, "Caption"):
            # for prop in drive.Properties_:
            #     print(prop.Name, "=", prop.Value)
            # print()
            if getattr(drive, "Size", None) is None:
                continue
            try:
                size_bytes = int(drive.Size)
            except (TypeError, ValueError):
                continue
            
            pnp = drive.PNPDeviceID
            if not pnp:
                continue
            
            try:
                if 'USBSTOR' in pnp:
                    i_product = pnp[pnp.index("PROD_") + 5 : pnp.index("&REV")].replace('_', ' ').title()
                elif 'SCSI' in pnp:
                    i_product = pnp.split("PROD_", 1)[1].split("\\", 1)[0].replace('_', ' ')
                    if "NVX" in i_product:
                        i_product = "Padlock NVX" if i_product == "PADLOCK NVX" else ""
                    elif "PORTABLE" in i_product:
                        i_product = "Aegis Portable" if i_product == " AEGIS PORTABLE" else ""
            except ValueError:
                i_product = ""

            size_gb = bytes_to_gb(size_bytes)
            
            drives_info.append({
                "caption": drive.Caption,
                "size_gb": size_gb,
                "iProduct": i_product,
                "pnpdeviceid": pnp
            })

    # print("wmi_usb_drives:")
    # pprint(drives_info)
    # print()
    return drives_info

def get_apricorn_libusb_data():
    """
    Use libusb to iterate over USB devices and collect info for Apricorn devices (VID '0984').
    Assign controller names in batch after enumeration.
    """
    devices = []
    ctx = ct.POINTER(usb.context)()
    rc = usb.init(ct.byref(ctx))
    if rc != 0:
        raise UsbTreeError("Failed to initialize libusb")
    try:
        dev_list = ct.POINTER(ct.POINTER(usb.device))()
        cnt = usb.get_device_list(ctx, ct.byref(dev_list))
        if cnt < 0:
            raise UsbTreeError("Failed to get device list")

        for i in range(cnt):
            dev = dev_list[i]
            desc = usb.device_descriptor()
            rc = usb.get_device_descriptor(dev, ct.byref(desc))
            if rc != 0:
                continue

            idVendor = f"{desc.idVendor:04x}"
            if idVendor != "0984":  # Filter for Apricorn devices
                continue

            # Core descriptors
            idProduct = f"{desc.idProduct:04x}"
            bcdDevice = f"{desc.bcdDevice:04x}"
            bcdUSB = float(parse_usb_version(desc.bcdUSB))
            bus_number = usb.get_bus_number(dev)
            dev_address = usb.get_device_address(dev)

            devices.append({
                "iProduct": idProduct,
                "bcdDevice": bcdDevice,
                "bcdUSB": bcdUSB,
                "bus_number": bus_number,
                "dev_address": dev_address
            })

        usb.free_device_list(dev_list, 1)

    finally:
        usb.exit(ctx)

    # print("libusb devices:")
    # pprint(devices)
    # print()
    return devices if devices else None

# ==================================
# Process Apricorn Device Info
# ==================================

def sort_wmi_drives(wmi_usb_devices, wmi_usb_drives):
    """
    Sorts the wmi_drives list to match the order of wmi_devices.

    Relies on matching serial numbers, handling variations like prefixes
    (e.g., 'MSFT30...') and serial numbers embedded in PNPDeviceIDs.
    Handles SCSI devices as a fallback if serial matching fails.
    """
    sorted_drives = []
    # Make a mutable copy to safely remove items from during processing
    drives_to_process = list(wmi_usb_drives)

    for device in wmi_usb_devices:
        device_serial = device.get('serial', '') # Use .get for safety
        device_desc = device.get('description', '')
        found_index = -1 # Index of the drive found in drives_to_process

        # Special handling for known SCSI devices based on description if serial is unreliable/absent
        is_scsi_device = 'SCSI' in device_desc or (device_serial and device_serial.startswith('MSFT30'))

        best_match_score = -1 # Use a score for better matching prio

        for i, drive in enumerate(drives_to_process):
            pnp_id = drive['pnpdeviceid']
            current_score = -1

            # Extract the instance ID part (usually after the last '\')
            instance_id = pnp_id.rsplit('\\', 1)[-1]

            # Extract the potential serial number part from the instance ID (before potential '&')
            ampersand_pos = instance_id.find('&')
            pnp_serial_part = instance_id[:ampersand_pos] if ampersand_pos != -1 else instance_id

            # --- Scoring Logic ---
            # Score 3: Exact match between device serial and PNP serial part
            if device_serial and device_serial == pnp_serial_part:
                current_score = 3
            # Score 2: Device serial contains PNP serial part OR vice-versa (Handles prefixes/suffixes)
            elif device_serial and pnp_serial_part and (pnp_serial_part in device_serial or device_serial in pnp_serial_part):
                 current_score = 2
            # Score 1: If it's a known SCSI device type and the drive is SCSI (fallback)
            elif is_scsi_device and "SCSI" in pnp_id and "PADLOCK_NVX" in pnp_id: # Be specific if possible
                 # Ensure this SCSI drive hasn't been matched by a higher score rule already
                 # This simplistic check assumes only one such SCSI drive.
                 current_score = 1

            # Update best match if current score is higher
            if current_score > best_match_score:
                best_match_score = current_score
                found_index = i

        # If a reasonably confident match was found (Score > 0)
        if found_index != -1 and best_match_score > 0:
            # Remove the drive from the processing list and append it to the sorted list.
            found_drive = drives_to_process.pop(found_index)
            sorted_drives.append(found_drive)
        else:
            # If no match found for this device, add a placeholder or handle error
            # For simplicity here, we'll append None, but you might need robust error handling
             print(f"Warning: No matching drive found for WMI device: {device_serial} / {device_desc}")
             sorted_drives.append(None) # Add placeholder

    # Append any remaining drives that were not matched to any device (might be unexpected drives)
    if drives_to_process:
        print(f"Warning: Appending {len(drives_to_process)} unmatched drives to the end:")
        pprint(drives_to_process)
        sorted_drives.extend(drives_to_process) # Or handle as errors

    # Filter out potential None placeholders if added
    sorted_drives_filtered = [drive for drive in sorted_drives if drive is not None]

    wmi_usb_drives = sorted_drives_filtered

    # # --- Output and Verification ---
    # print("SORTED ----------")
    # print("wmi_usb_devices: ")
    # pprint(wmi_usb_devices)
    # print()
    # print("wmi_usb_drives: ")
    # pprint(wmi_usb_drives)
    # return wmi_usb_drives
    return wmi_usb_drives

def sort_usb_controllers(wmi_usb_devices, usb_controllers):
    # --- Sorting Logic ---
    sorted_controllers = []
    # Make a mutable copy to safely remove items from during processing
    controllers_to_process = list(usb_controllers)

    for device in wmi_usb_devices:
        target_serial = device['serial']
        found_index = -1 # Index of the controller found in controllers_to_process

        # Iterate through the remaining controllers to find a match for the current device
        for i, controller in enumerate(controllers_to_process):
            device_id = controller['DeviceID']

            # Extract the part after the last backslash, which should be the serial
            # Use rsplit with maxsplit=1 for efficiency and correctness
            parts = device_id.rsplit('\\', 1)
            if len(parts) == 2:
                extracted_serial = parts[1]
                # Check if the extracted serial matches the target serial from the device list
                if extracted_serial == target_serial:
                    found_index = i
                    break # Found the controller for this device, stop searching
            # else: If DeviceID format is unexpected (no '\'), it won't match.

        if found_index != -1:
            # If a match was found, remove the controller from the processing list
            # and append it to the sorted list.
            found_controller = controllers_to_process.pop(found_index)
            sorted_controllers.append(found_controller)
        else:
            # This case might indicate an issue if a device doesn't have a corresponding controller
            print(f"Warning: No matching controller found for device serial: {target_serial}")

    # Check if any controllers were left unmatched (should be empty if data is consistent)
    if controllers_to_process:
        print("Warning: Some controllers were not matched and are being appended:")
        pprint(controllers_to_process)
        sorted_controllers.extend(controllers_to_process)
    usb_controllers = sorted_controllers

    # --- Output and Verification ---
    # print("wmi_usb_devices: ")
    # pprint(wmi_usb_devices)
    # print()
    # print("usb_controllers: ")
    # pprint(usb_controllers)
    return usb_controllers

def sort_libusb_data(wmi_usb_devices, libusb_data):
    """
    Attempt to match libusb entries to wmi_usb_devices by pid and best-match bcdUSB.
    Avoids hardcoding serial numbers.
    """
    if not libusb_data:
        raise UsbTreeError("No libusb_data available to sort")

    # Build lookup: {pid: [libusb_entry, ...]}
    from collections import defaultdict
    pid_map = defaultdict(list)
    for entry in libusb_data:
        pid_map[entry['iProduct']].append(entry)

    sorted_libusb = []
    used_entries = set()

    for device in wmi_usb_devices:
        pid = device['pid']
        candidates = pid_map.get(pid, [])

        if not candidates:
            print(f"Warning: No libusb entry found for PID {pid}")
            sorted_libusb.append({
                "iProduct": pid,
                "bcdDevice": "0000",
                "bcdUSB": 0.0,
                "bus_number": -1,
                "dev_address": -1
            })
            continue

        # Select candidate with highest bcdUSB (assuming newest / best match)
        best = max(candidates, key=lambda x: x['bcdUSB'])
        key = (best['iProduct'], best['bcdDevice'])

        if key in used_entries:
            # Fall back to any not yet used candidate
            unused = [c for c in candidates if (c['iProduct'], c['bcdDevice']) not in used_entries]
            if unused:
                best = unused[0]
                key = (best['iProduct'], best['bcdDevice'])
            else:
                print(f"Warning: All libusb entries for PID {pid} already used")
                best = candidates[0]  # fallback anyway

        used_entries.add(key)
        sorted_libusb.append(best)
    libusb_data = sorted_libusb

    # --- Output and Verification ---
    # print("wmi_usb_devices: ")
    # pprint(wmi_usb_devices)
    # print()
    # print("usb_controllers: ")
    # pprint(usb_controllers)
    return libusb_data

def instantiate_class_objects(wmi_usb_devices, wmi_usb_drives, usb_controllers, libusb_data):
    devices = []
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

    # print()
    # print("----------")
    # print("AFTER PROCESSING: ")
    # print("USB Controllers:")
    # pprint(usb_controllers)
    # print()
    # print("wmi_usb_devices:")
    # pprint(wmi_usb_devices)
    # print()
    # print("wmi_usb_drives:")
    # pprint(wmi_usb_drives)
    # print()
    # print("libusb devices:")
    # pprint(libusb_data)
    # print("----------")

    for item in range(len(wmi_usb_devices)):
        idProduct = wmi_usb_devices[item]['pid']
        idVendor = wmi_usb_devices[item]['vid']
        bcdDevice = libusb_data[item]['bcdDevice']
        bcdUSB = libusb_data[item]['bcdUSB']
        iManufacturer = wmi_usb_devices[item]['manufacturer']
        iProduct = wmi_usb_drives[item]['iProduct']
        usbController = usb_controllers[item]['ControllerName']
        bus_number = libusb_data[item]['bus_number']
        dev_address = libusb_data[item]['dev_address']

        if wmi_usb_devices[item]['serial'].startswith('MSFT30'):
            SCSIDevice = True
            iSerial = wmi_usb_devices[item]['serial'][6:]
        else:
            SCSIDevice = False
            iSerial = wmi_usb_devices[item]['serial']

        driveSizeGB = find_closest(wmi_usb_drives[item]["size_gb"], closest_values[idProduct][1])

        # Create device info without usbController for now
        dev_info = WinUsbDeviceInfo(
            bcdUSB=bcdUSB,
            idVendor=idVendor,
            idProduct=idProduct,
            bcdDevice=bcdDevice,
            iManufacturer=iManufacturer,
            iProduct=iProduct,
            iSerial=iSerial,
            SCSIDevice=SCSIDevice,
            driveSizeGB=driveSizeGB,
            usbController=usbController,
            busNumber=bus_number,
            deviceAddress=dev_address
        )
        devices.append(dev_info)
    return devices if devices else None

# ==================================
# Main
# ==================================

def find_apricorn_device():
    """
    High-level function tying together WMI USB device data, drive data, and libusb data.
    Returns a list of WinUsbDeviceInfo objects or None if none found.
    """
    wmi_usb_devices = get_wmi_usb_devices()
    wmi_usb_drives = get_wmi_usb_drives()
    usb_controllers = get_all_usb_controller_names()
    libusb_data = get_apricorn_libusb_data()

    wmi_usb_drives = sort_wmi_drives(wmi_usb_devices, wmi_usb_drives)
    usb_controllers = sort_usb_controllers(wmi_usb_devices, usb_controllers)
    libusb_data = sort_libusb_data(wmi_usb_devices, libusb_data)

    apricorn_devices = instantiate_class_objects(wmi_usb_devices, wmi_usb_drives, usb_controllers, libusb_data)
    return apricorn_devices

def main():
    """Find and display information about Apricorn devices."""
    devices = find_apricorn_device()
    if devices:
        for idx, dev in enumerate(devices, 1):
            print(f"\n=== Apricorn Device #{idx} ===")
            pprint(vars(dev))
        print()
    else:
        print("No Apricorn devices found.")

if __name__ == '__main__':
    main()
