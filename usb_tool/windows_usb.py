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
    idProduct: str
    idVendor: str
    bcdDevice: str
    bcdUSB: float
    iManufacturer: str
    iProduct: str
    iSerial: str
    usbController: str = ""
    SCSIDevice: bool = False
    driveSizeGB: int = 0
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

def match_devices(wmi_usb_devices, wmi_usb_drives, usb_controllers, libusb_data):
    """
    Match and consolidate USB device information from multiple data sources.

    This function iterates over entries in `wmi_usb_devices` and attempts to
    find corresponding entries in `usb_controllers`, `libusb_data`, and
    `wmi_usb_drives` based on matching product IDs (PIDs) or expected product
    names. It then constructs a list of `WinUsbDeviceInfo` objects that contain
    merged information from all four sources.

    Args:
        wmi_usb_devices (list of dict): 
            A list of dictionaries, each containing information about a USB
            device from WMI. Example keys include:
            - "pid": The product ID of the USB device (string).
            - "vid": The vendor ID of the USB device (string).
            - "manufacturer": The manufacturer string.
            - "serial": The serial string (includes a prefix that may indicate SCSI).
        wmi_usb_drives (list of dict): 
            A list of dictionaries with additional drive-specific info, such as:
            - "iProduct": A human-readable name for the product.
            - "size_gb": Numeric size of the drive in gigabytes.
        usb_controllers (list of dict): 
            A list of dictionaries representing USB controllers, with keys like:
            - "DeviceID": A string that contains the PID.
            - "ControllerName": A human-readable name for the USB controller.
        libusb_data (list of dict): 
            A list of dictionaries from libusb or a similar library, containing:
            - "iProduct": The product ID string (used for matching).
            - "bcdDevice": The device release number in binary-coded decimal.
            - "bcdUSB": The USB specification version in binary-coded decimal.
            - "bus_number": The bus number to which the device is attached.
            - "dev_address": The device address on that bus.

    Returns:
        list of WinUsbDeviceInfo or None:
            Returns a list of `WinUsbDeviceInfo` objects that consolidate
            details from all inputs. If no matches were made, returns `None`.

    Note:
        - This function modifies the original lists (`wmi_usb_devices`,
          `usb_controllers`, `libusb_data`, and `wmi_usb_drives`) by popping
          and reinserting matched items to align indices.
        - The function uses an internal `closest_values` mapping to find valid
          or approximate drive sizes.
        - A helper function `find_closest` (not shown here) is assumed to be
          available for matching the numeric drive size to a predefined list.
    """
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
    
    for item in range(len(wmi_usb_devices)): #start loop over wmi_usb_devices
        for index in range(len(usb_controllers)): #find match in usb_controllers
            if wmi_usb_devices[item]['pid'] in usb_controllers[index]['DeviceID']: #match pid from wmi_usb_devices to usb_controllers
                matched_item = usb_controllers.pop(index)
                usb_controllers.insert(item, matched_item)
                break
        for index in range(len(libusb_data)): #find match in libusb_data
            if wmi_usb_devices[item]['pid'] in libusb_data[index]['iProduct']: #match pid from wmi_usb_devices to libusb_data
                matched_item = libusb_data.pop(index)
                libusb_data.insert(item, matched_item)
                break
        for index in range(len(wmi_usb_drives)): #find match in wmi_usb_drives
            for x in closest_values:
                if wmi_usb_drives[index]['iProduct'] == closest_values[x][0]:
                    matched_item = wmi_usb_drives.pop(index)
                    wmi_usb_drives.insert(item, matched_item)

    for item in range(len(wmi_usb_devices)):
        idProduct = wmi_usb_devices[item]['pid']
        idVendor = wmi_usb_devices[item]['vid']
        bcdDevice = libusb_data[item]['bcdDevice']
        bcdUSB = libusb_data[item]['bcdUSB']
        iManufacturer = wmi_usb_devices[item]['manufacturer']
        iProduct = wmi_usb_drives[item]['iProduct']
        iSerial = wmi_usb_devices[item]['serial'][6:]
        usbController = usb_controllers[item]['ControllerName']
        bus_number = libusb_data[item]['bus_number']
        dev_address = libusb_data[item]['dev_address']

        if wmi_usb_devices[item]['serial'].startswith('MSFT30'):
            SCSIDevice = True
        else:
            SCSIDevice = False

        driveSizeGB = find_closest(wmi_usb_drives[item]["size_gb"], closest_values[idProduct][1])

        # Create device info without usbController for now
        dev_info = WinUsbDeviceInfo(
            idProduct=idProduct,
            idVendor=idVendor,
            bcdDevice=bcdDevice,
            bcdUSB=bcdUSB,
            iManufacturer=iManufacturer,
            iProduct=iProduct,
            iSerial=iSerial,
            usbController=usbController,
            SCSIDevice=SCSIDevice,
            driveSizeGB=driveSizeGB,
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
    apricorn_devices = match_devices(get_wmi_usb_devices(), get_wmi_usb_drives(), get_all_usb_controller_names(), get_apricorn_libusb_data())
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
