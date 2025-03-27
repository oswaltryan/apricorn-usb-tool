import libusb as usb
import ctypes as ct
from dataclasses import dataclass
import subprocess
from pprint import pprint
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
    return f"{closest}GB"

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

def _get_usb_controller_name(idVendor: str, iSerial: str) -> str:
    """Retrieve the USB controller name using PowerShell."""
    ps_script = rf'''
    $vendor = "{idVendor}"
    $serial = "{iSerial}"
    Get-CimInstance Win32_USBControllerDevice | ForEach-Object {{
        $device = Get-CimInstance -CimInstance $_.Dependent
        if ($device.DeviceID -like "*VID_$vendor*" -and $device.DeviceID -like "*$serial*") {{
            $controller = Get-CimInstance -CimInstance $_.Antecedent
            $controller.Name
        }}
    }}
    '''
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True
    )
    return result.stdout.strip().split('\n')[0] if result.stdout else ""

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
    bcdUSB: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    usbController: str = ""
    SCSIDevice: str = ""
    driveSize: str = ""
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
    query = "SELECT * FROM Win32_DiskDrive WHERE InterfaceType='USB'"
    usb_drives = service.ExecQuery(query)
    drives_info = []
    closest_values = [16, 30, 60, 120, 240, 480, 1000, 2000]
    
    for drive in usb_drives:
        if getattr(drive, "Size", None) is None:
            continue
        try:
            size_bytes = int(drive.Size)
        except (TypeError, ValueError):
            continue
        
        size_gb = bytes_to_gb(size_bytes)
        closest_match = find_closest(size_gb, closest_values)
        
        pnp = drive.PNPDeviceID
        if not pnp:
            continue
        
        try:
            i_product = pnp[pnp.index("PROD_") + 5 : pnp.index("&REV")].replace('_', ' ')
        except ValueError:
            i_product = ""
        
        drives_info.append({
            "caption": drive.Caption,
            "size_gb": size_gb,
            "closest_match": closest_match,
            "iProduct": i_product,
            "pnpdeviceid": pnp
        })

    return drives_info

# ==================================
# Gathering Apricorn Device Info
# ==================================

def get_apricorn_libusb_data(wmi_usb_devices, usb_drives, _get_usb_controller_name):
    """
    Use libusb to iterate over USB devices and collect info for Apricorn devices (VID '0984').
    Matches devices uniquely using serial numbers and ensures correct drive size assignment.
    Overrides iProduct with drive-specific data when available.
    """
    devices = []
    used_serials = set()  # Track processed serial numbers to avoid duplicates
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
            bcdUSB = parse_usb_version(desc.bcdUSB)
            bus_number = usb.get_bus_number(dev)
            dev_address = usb.get_device_address(dev)

            # Create empty fields for descriptors we're filling in.
            iManufacturer = iProduct = iSerial = ""

            # If libusb serial is empty or not unique, fall back to WMI with VID/PID/serial matching
            if not iSerial or iSerial in used_serials:
                matching_wmi = next((item for item in wmi_usb_devices 
                                     if item['vid'] == idVendor and item['pid'] == idProduct 
                                     and item['serial'] not in used_serials), None)
                if matching_wmi:
                    wmi_serial = matching_wmi['serial']
                    if wmi_serial.startswith('MSFT30'):
                        SCSIDevice = 'True'
                        iSerial = wmi_serial[6:]
                    else:
                        SCSIDevice = 'False'
                        iSerial = wmi_serial
                    iManufacturer = matching_wmi['manufacturer']
                    iProduct = matching_wmi['description']
                else:
                    SCSIDevice = 'False'
                    iSerial = f"Unknown_{bus_number}_{dev_address}"  # Fallback unique ID
            else:
                SCSIDevice = 'False'  # Assume non-MSFT30 unless WMI overrides
                matching_wmi = next((item for item in wmi_usb_devices 
                                     if item['vid'] == idVendor and item['pid'] == idProduct 
                                     and (item['serial'] == iSerial or 
                                          (item['serial'].startswith('MSFT30') and item['serial'][6:] == iSerial))), None)
                if matching_wmi:
                    iManufacturer = matching_wmi['manufacturer']
                    iProduct = matching_wmi['description']
                    if matching_wmi['serial'].startswith('MSFT30'):
                        SCSIDevice = 'True'

            # Mark serial as used
            used_serials.add(iSerial)

            # Match with USB drives for drive size and override iProduct
            driveSize = "N/A"
            if iSerial:
                for drive in usb_drives:
                    pnp = drive.get("pnpdeviceid")
                    if pnp and iSerial in pnp:
                        driveSize = drive["closest_match"]
                        if drive.get("iProduct"):
                            iProduct = drive["iProduct"]  # Your fix: override iProduct
                        break

            # Get USB controller name
            controller_name = _get_usb_controller_name(idVendor, iSerial)
            usbController = ('Intel' if 'Intel' in controller_name else 
                             'ASMedia' if 'ASMedia' in controller_name else controller_name)

            # Build device info object
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
                driveSize=driveSize,
                busNumber=bus_number,
                deviceAddress=dev_address
            )
            devices.append(dev_info)

        usb.free_device_list(dev_list, 1)
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
    apricorn_devices = get_apricorn_libusb_data(wmi_usb_data, usb_drives, _get_usb_controller_name)
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
