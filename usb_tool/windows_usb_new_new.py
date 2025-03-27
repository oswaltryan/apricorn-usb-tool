import libusb as usb
import ctypes as ct
from dataclasses import dataclass
import subprocess
from pprint import pprint
import win32com.client

# Configure libusb to use the included libusb-1.0.dll
usb.config(LIBUSB=None)


# ==================================
#          Helper Functions
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

def dump_device_config(handle):
    """Dumps the active configuration and its endpoints for debugging."""
    dev = usb.get_device(handle)
    dev_desc = usb.device_descriptor()
    rc = usb.get_device_descriptor(dev, ct.byref(dev_desc))
    if rc < 0:
        print(f"  - Failed to get device descriptor: {rc}")
        return

    config_ptr = ct.POINTER(usb.config_descriptor)()
    rc = usb.get_active_config_descriptor(dev, ct.byref(config_ptr))
    if rc < 0:
        print(f"  - Failed to get configuration descriptor: {rc}")
        return

    try:
        config = config_ptr.contents
        print(f"\n  [*] Dumping Device Configuration...")
        print(f"  - Total Configurations Available: {dev_desc.bNumConfigurations}")
        print(f"  - Active Configuration: {config.bConfigurationValue}")
        print(f"  - Number of Interfaces: {config.bNumInterfaces}")

        for i in range(config.bNumInterfaces):
            interface = config.interface[i]
            for alt in range(interface.num_altsetting):
                intf_desc = interface.altsetting[alt]
                print(f"  - Interface {intf_desc.bInterfaceNumber}, Alt Setting {intf_desc.bAlternateSetting}")
                print(f"    Number of Endpoints: {intf_desc.bNumEndpoints}")

                for ep_idx in range(intf_desc.bNumEndpoints):
                    ep = intf_desc.endpoint[ep_idx]
                    ep_addr = ep.bEndpointAddress
                    ep_type = ep.bmAttributes & 0x03
                    direction = "IN" if (ep_addr & 0x80) else "OUT"
                    types = {0: "Control", 1: "Isochronous", 2: "Bulk", 3: "Interrupt"}
                    print(f"    - Endpoint 0x{ep_addr:02x} ({direction}, {types.get(ep_type, 'Unknown')})")
    finally:
        usb.free_config_descriptor(config_ptr)

def _get_usb_controller_name(idVendor: str, iSerial: str) -> str:
    """Retrieve the USB controller name using PowerShell."""
    ps_script = rf'''
        $vendor = "{idVendor}"
        $serial = "{iSerial}"
        Get-CimInstance Win32_USBControllerDevice | ForEach-Object {{
            $device = Get-CimInstance -CimInstance $_.Dependent
            # Check that the DeviceID contains both VID_{idVendor} and iSerial
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
    # Return the first line of output if it exists
    return result.stdout.strip().split('\n')[0] if result.stdout else ""


# ==================================
#   Dataclasses and Custom Errors
# ==================================

class UsbTreeError(Exception):
    """Custom exception for USB tree errors."""
    pass

@dataclass
class WinUsbDeviceInfo:
    """
    Dataclass representing a USB device information structure.
    Now includes busNumber and deviceAddress to help differentiate
    multiple devices that might share the same VID/PID/Serial.
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
#         WMI Connections
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
        
        # Attempt to parse the iProduct from PNPDeviceID
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
#  Gathering Apricorn Device Info
# ==================================

def get_apricorn_libusb_data(wmi_usb_devices, usb_drives, _get_usb_controller_name):
    """
    Use libusb to iterate over USB devices and collect info for
    Apricorn devices (VID '0984'). Merge with WMI/drive data.
    This version includes busNumber/deviceAddress to differentiate
    devices that share the same VID/PID/serial but exist on different
    ports or addresses.
    """

    # Modify original list to keep only Apricorn devices, skipping those without manufacturer
    wmi_usb_devices[:] = [item for item in wmi_usb_devices if item.get('manufacturer') == 'Apricorn']
    # print(">> WMI Devices")
    # pprint(wmi_usb_devices)
    # print()

    # print(">> USB Drives")
    # pprint(usb_drives)
    # print()

    devices = []
    # for i in range(len(wmi_usb_devices)):
    #     device_obj = WinUsbDeviceInfo(
    #         idProduct=wmi_usb_devices[i]['pid'],
    #         idVendor=wmi_usb_devices[i]['vid'],
    #         iManufacturer=wmi_usb_devices[i]['manufacturer'],
    #         iProduct=usb_drives[i]['iProduct'],
    #         iSerial=wmi_usb_devices[i]['serial'],
    #         driveSize=usb_drives[i]['closest_match'],
    #         bcdDevice="",
    #         bcdUSB=""
    #     )
    #     devices.append(device_obj)

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

            field_values = {}
            for field, field_type in desc._fields_:
                value = getattr(desc, field)
                # Convert integer values to hex
                if isinstance(value, int):
                    # Format with leading zeros if desired (adjust width as needed)
                    field_values[field] = f"0x{value:04x}"
                else:
                    field_values[field] = value
            pprint(field_values)

            # Check if Apricorn device by VID
            idVendor = f"{desc.idVendor:04x}"
            if idVendor != "0984":
                continue

            # Grab core descriptors
            idProduct = f"{desc.idProduct:04x}"
            bcdDevice = f"{desc.bcdDevice:04x}"
            bcdUSB = parse_usb_version(desc.bcdUSB)
            iSerialNumber = f"{desc.iSerialNumber:04x}"

            # Retrieve bus number and device address
            bus_number = usb.get_bus_number(dev)
            dev_address = usb.get_device_address(dev)



            # # Get the USB controller name
            # controller_name = _get_usb_controller_name(idVendor, iSerial)
            # # Simplify or rename based on known vendor strings
            # if 'Intel' in controller_name:
            #     controller_name = 'Intel'
            # elif 'ASMedia' in controller_name:
            #     controller_name = 'ASMedia'

            # Build the final device info object
            dev_info = WinUsbDeviceInfo(
                idProduct=idProduct,
                idVendor=idVendor,
                bcdDevice=bcdDevice,
                bcdUSB=bcdUSB,
                iManufacturer="",
                iProduct="",
                iSerial=iSerialNumber,
                usbController="",
                driveSize="",
                busNumber=bus_number,
                deviceAddress=dev_address
            )
            devices.append(dev_info)

        usb.free_device_list(dev_list, 1)

    finally:
        usb.exit(ctx)

    return devices if devices else None


# ==================================
#             Main
# ==================================

def find_apricorn_device():
    """
    High-level function that ties together:
      - WMI USB device data
      - WMI USB drive data
      - libusb data for Apricorn devices (VID '0984')
    Returns a list of WinUsbDeviceInfo objects, or None if none found.
    """
    wmi_usb_data = get_wmi_usb_devices()   # WMI PnP USB info
    usb_drives = get_wmi_usb_drives()      # WMI USB drive info

    # For debugging, show the drives
    # print(">>> WMI USB Drives:")
    # pprint(usb_drives)
    # print()

    # Gather Apricorn device info via libusb
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
