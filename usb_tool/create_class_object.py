from pprint import pprint
from dataclasses import dataclass

@dataclass
class WinUsbDeviceInfo:
    """
    Dataclass representing a USB device information structure.
    Now includes busNumber and deviceAddress to help differentiate
    multiple devices that might share the same VID/PID/Serial.
    """
    idProduct: str
    idVendor: str
    iManufacturer: str
    iProduct: str
    iSerial: str
    driveSize: str = ""

wmi_usb_devices = [
    {'description': 'Apricorn Secure Key', 'manufacturer': 'Apricorn', 'pid': '1407', 'serial': '160050000012', 'vid': '0984'},
    {'description': 'Apricorn Secure Key', 'manufacturer': 'Apricorn', 'pid': '1407', 'serial': 'MSFT30000000000014', 'vid': '0984'},
    {'description': 'Apricorn Secure Key', 'manufacturer': 'Apricorn', 'pid': '1410', 'serial': '141420000016', 'vid': '0984'}
]

wmi_usb_drives = [
    {'caption': 'Apricorn Secure Key 3.0 USB Device', 'closest_match': '16GB', 'iProduct': 'SECURE KEY 3.0', 'pnpdeviceid': 'USBSTOR\\DISK&VEN_APRICORN&PROD_SECURE_KEY_3.0&REV_0803\\141420000016&0', 'size_gb': 14.623682498931885},
    {'caption': 'Apricorn Secure Key 3.0 USB Device', 'closest_match': '120GB', 'iProduct': 'SECURE KEY 3.0', 'pnpdeviceid': 'USBSTOR\\DISK&VEN_APRICORN&PROD_SECURE_KEY_3.0&REV_0457\\160050000012&0', 'size_gb': 111.78805589675903},
    {'caption': 'Apricorn Secure Key 3.0 USB Device', 'closest_match': '16GB', 'iProduct': 'SECURE KEY 3.0', 'pnpdeviceid': 'USBSTOR\\DISK&VEN_APRICORN&PROD_SECURE_KEY_3.0&REV_0456\\000000000014&0', 'size_gb': 14.907116889953613}
]

devices = []

for i in range(len(wmi_usb_devices)):
    device_obj = WinUsbDeviceInfo(
        idProduct=wmi_usb_devices[i]['pid'],
        idVendor=wmi_usb_devices[i]['vid'],
        iManufacturer=wmi_usb_devices[i]['manufacturer'],
        iProduct=wmi_usb_drives[i]['iProduct'],
        iSerial=wmi_usb_devices[i]['serial'],
        driveSize=wmi_usb_drives[i]['closest_match']
    )
    devices.append(device_obj)

# Now you can print devices:
for device in range(len(devices)):
    pprint(devices[device])
    print()
