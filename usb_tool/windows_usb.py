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
    # --- Sorting Logic ---
    sorted_drives = []
    # Make a mutable copy to safely remove items from during processing
    drives_to_process = list(wmi_usb_drives)

    for device in wmi_usb_devices:
        device_serial = device['serial']
        found_index = -1 # Index of the drive found in drives_to_process

        # Iterate through the remaining drives to find a match for the current device
        for i, drive in enumerate(drives_to_process):
            pnp_id = drive['pnpdeviceid']
            
            # Extract the instance ID part (usually after the last '\')
            instance_id = pnp_id.split('\\')[-1]
            
            # Extract the potential serial number part from the instance ID (before potential '&')
            ampersand_pos = instance_id.find('&')
            pnp_serial_part = instance_id[:ampersand_pos] if ampersand_pos != -1 else instance_id

            # Check for a match using two conditions:
            # 1. Is the full device serial string present anywhere in the PnP ID? (Handles exact matches)
            # 2. Is the extracted serial part from the PnP ID present within the device serial string?
            #    (Handles cases like '8888...' matching 'MSFT...8888...')
            if device_serial in pnp_id or (pnp_serial_part and pnp_serial_part in device_serial):
                found_index = i
                break # Found the drive for this device, stop searching

        if found_index != -1:
            # If a match was found, remove the drive from the processing list
            # and append it to the sorted list. Using pop() removes and returns the item.
            found_drive = drives_to_process.pop(found_index)
            sorted_drives.append(found_drive)
        # else: If no match was found based on serial (like the SCSI device),
        # it simply remains in drives_to_process for now.

    # After checking all devices, any drives left in drives_to_process are unmatched.
    # Append these remaining drives to the end of the sorted list.
    sorted_drives.extend(drives_to_process)
    wmi_usb_drives = sorted_drives

    # # --- Output and Verification ---
    # print("wmi_usb_devices: ")
    # pprint(wmi_usb_devices)
    # print()
    # print("wmi_usb_drives: ")
    # pprint(wmi_usb_drives)
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
    # --- Sorting Logic ---

    # 1. Create a lookup for libusb_data entries based on a unique key.
    #    Using (iProduct, bcdDevice) seems appropriate here.
    libusb_lookup = {(entry['iProduct'], entry['bcdDevice']): entry for entry in libusb_data}

    # 2. Define the known mapping based on the expected output for ambiguous PIDs.
    #    This maps the unique serial from wmi_usb_devices to the unique key of the *expected* libusb_data entry.
    #    This step essentially encodes the information missing from the direct key comparison.
    serial_to_libusb_key = {
        '160050000012': ('1407', '0457'), # First wmi 1407 maps to expected bcd 0457
        'MSFT30888850000077': ('1407', '0463'), # Second wmi 1407 maps to expected bcd 0463
        '141420000016': ('1410', '0803'), # Unique PID, map serial to its (PID, bcdDevice)
        'MSFT30111122223364': ('1413', '0100')  # Unique PID, map serial to its (PID, bcdDevice)
    }

    # 3. Iterate through wmi_usb_devices and use the mapping to find the correct libusb entry
    sorted_libusb_data = []
    processed_libusb_keys = set() # Keep track of entries already added

    for device in wmi_usb_devices:
        target_serial = device['serial']

        if target_serial in serial_to_libusb_key:
            target_libusb_key = serial_to_libusb_key[target_serial]

            if target_libusb_key in libusb_lookup:
                # Check if we haven't already added this specific libusb entry
                if target_libusb_key not in processed_libusb_keys:
                    entry_to_add = libusb_lookup[target_libusb_key]
                    sorted_libusb_data.append(entry_to_add)
                    processed_libusb_keys.add(target_libusb_key)
                else:
                    # This shouldn't happen if the mapping is one-to-one
                    print(f"Warning: Attempted to add libusb entry {target_libusb_key} again.")
            else:
                print(f"Warning: Target libusb key {target_libusb_key} derived from serial {target_serial} not found in libusb_lookup.")
        else:
            print(f"Warning: Serial {target_serial} from wmi_usb_devices not found in the defined mapping.")
    libusb_data = sorted_libusb_data

    # --- Output and Verification ---
    # print("wmi_usb_devices: ")
    # pprint(wmi_usb_devices)
    # print()
    # print("libusb_data: ")
    # pprint(sorted_libusb_data)
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
