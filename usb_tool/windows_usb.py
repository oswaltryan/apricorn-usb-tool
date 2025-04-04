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
    Retrieve a mapping of USB DeviceIDs to controller names for Apricorn devices (VID '0984').
    Returns a dictionary: {device_id: controller_name}.
    """
    ps_script = '''
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
        return {}
    try:
        data = json.loads(result.stdout)
        # If data is a single object (not a list), wrap it in a list
        if isinstance(data, dict):
            data = [data]
        # Normalize DeviceID to uppercase for consistent matching
        return {item['DeviceID'].upper(): item['ControllerName'] for item in data}
    except json.JSONDecodeError:
        print("Failed to parse PowerShell output")
        return {}

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
# WMI Connections
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
        if not device_id.upper().startswith("USB\\VID_"):
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
            "manufacturer": device.Manufacturer or "",
            "description": device.Description or "",
            "serial": serial
        })

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
                    i_product = "Padlock NVX" if i_product == "PADLOCK NVX" else ""
            except ValueError:
                i_product = ""

            closest_values = [16, 30, 60, 120, 240, 480, 1000, 2000]
            size_gb = bytes_to_gb(size_bytes)
            closest_match = find_closest(size_gb, closest_values)
            
            drives_info.append({
                "caption": drive.Caption,
                "size_gb": size_gb,
                # "closest_match": closest_match,
                "iProduct": i_product,
                "pnpdeviceid": pnp
            })

    return drives_info

# ==================================
# Gathering Apricorn Device Info
# ==================================

def get_apricorn_libusb_data(wmi_usb_devices, usb_drives, get_all_usb_controller_names):
    """
    Use libusb to iterate over USB devices and collect info for Apricorn devices (VID '0984').
    Assign controller names in batch after enumeration.
    """
    devices = []
    used_serials = set()
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

            iManufacturer = iProduct = iSerial = ""
            if not iSerial or iSerial in used_serials:
                matching_wmi = next((item for item in wmi_usb_devices 
                                     if item['vid'] == idVendor and item['pid'] == idProduct 
                                     and item['serial'] not in used_serials), None)
                if matching_wmi:
                    wmi_serial = matching_wmi['serial']
                    if wmi_serial.startswith('MSFT30'):
                        SCSIDevice = True
                        iSerial = wmi_serial[6:]
                        iManufacturer = matching_wmi['manufacturer'] if matching_wmi['manufacturer'] == "Apricorn" else ""
                    else:
                        SCSIDevice = False
                        iSerial = wmi_serial
                        iManufacturer = matching_wmi['manufacturer']
                        iProduct = matching_wmi['description']
                else:
                    SCSIDevice = False
                    iSerial = f"Unknown_{bus_number}_{dev_address}"
            else:
                SCSIDevice = False
                matching_wmi = next((item for item in wmi_usb_devices 
                                     if item['vid'] == idVendor and item['pid'] == idProduct 
                                     and (item['serial'] == iSerial or 
                                          (item['serial'].startswith('MSFT30') and item['serial'][6:] == iSerial))), None)
                if matching_wmi:
                    iManufacturer = matching_wmi['manufacturer']
                    if matching_wmi['serial'].startswith('MSFT30'):
                        SCSIDevice = True

            used_serials.add(iSerial)

            closest_values = {
                "0310": [256, 500, 1000, 2000, 4000, 8000, 16000],
                "0315": [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000],
                "1400": [256, 500, 1000, 2000, 4000, 8000, 16000],
                "1405": [240, 480, 1000, 2000, 4000],
                "1406": [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000],
                "1407": [16, 30, 60, 120, 240, 480, 1000, 2000, 4000],
                "1408": [500, 512, 1000, 2000, 4000, 5000, 8000, 16000, 20000],
                "1409": [16, 32, 64, 128],
                "1410": [4, 8, 16, 32, 64, 128, 256, 512],
                "1413": [500, 1000, 2000],
            }
            driveSizeGB = "N/A"
            if iSerial:
                for drive in usb_drives:
                    pnp = drive.get("pnpdeviceid")
                    if SCSIDevice and "NVX" in pnp:
                        iProduct = drive['iProduct']
                        iManufacturer = "Apricorn"
                        closest_match = find_closest(drive["size_gb"], closest_values[idProduct])
                        drive.update({"closest_match": closest_match})
                        driveSizeGB = drive["closest_match"]
                        if drive.get("iProduct"):
                            iProduct = drive["iProduct"]
                        break
                    else:
                        if pnp and iSerial in pnp:
                            closest_match = find_closest(drive["size_gb"], closest_values[idProduct])
                            drive.update({"closest_match": closest_match})
                            driveSizeGB = drive["closest_match"]
                            if drive.get("iProduct"):
                                iProduct = drive["iProduct"]
                            break

            # Create device info without usbController for now
            dev_info = WinUsbDeviceInfo(
                idProduct=idProduct,
                idVendor=idVendor,
                bcdDevice=bcdDevice,
                bcdUSB=bcdUSB,
                iManufacturer=iManufacturer,
                iProduct=iProduct,
                iSerial=iSerial,
                usbController="",  # Set later
                SCSIDevice=SCSIDevice,
                driveSizeGB=driveSizeGB,
                busNumber=bus_number,
                deviceAddress=dev_address
            )
            devices.append(dev_info)

        usb.free_device_list(dev_list, 1)

        # Batch assign USB controller names
        if devices:
            controller_dict = get_all_usb_controller_names()
            for dev in devices:
                if dev.SCSIDevice:
                    device_id = f"USB\\VID_{dev.idVendor}&PID_{dev.idProduct}\\MSFT30{dev.iSerial}".upper()
                    controller_name = controller_dict.get(device_id, "")
                    dev.usbController = ('Intel' if 'Intel' in controller_name else 
                                        'ASMedia' if 'ASMedia' in controller_name else controller_name)
                else:
                    device_id = f"USB\\VID_{dev.idVendor}&PID_{dev.idProduct}\\{dev.iSerial}".upper()
                    controller_name = controller_dict.get(device_id, "")
                    dev.usbController = ('Intel' if 'Intel' in controller_name else 
                                        'ASMedia' if 'ASMedia' in controller_name else controller_name)

    finally:
        usb.exit(ctx)

    return devices if devices else None

# ==================================
# Main
# ==================================

def find_apricorn_device():
    """
    High-level function tying together WMI USB device data, drive data, and libusb data.
    Returns a list of WinUsbDeviceInfo objects or None if none found.
    """
    wmi_usb_data = get_wmi_usb_devices()
    usb_drives = get_wmi_usb_drives()
    apricorn_devices = get_apricorn_libusb_data(wmi_usb_data, usb_drives, get_all_usb_controller_names)
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
