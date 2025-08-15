

## Overview
This documentation provides instructions on how to install our Apricorn device USB library and use the `find_apricorn_device` function to detect, enumerate, and interact with Apricorn USB devices using **libusb** and **WMI**.

## Prerequisites
Tested on Python 3.9‑3.12.
### 1. (Optional) Create a Virtual Environment
```sh
python -m venv venv
```

Activate the virtual environment:
- **Linux/macOS:**
  ```sh
  source venv/bin/activate
  ```
- **Windows:**
  ```sh
  venv\Scripts\activate
  ```

### 2. Install the Package
Install the tool and its dependencies directly using `pyproject.toml`:
```sh
pip install .
```

### 3. Invoke the USB Detection Script
Run the script anywhere:
```sh
usb
```

---

## Using `find_apricorn_device`

### Function Purpose
The `find_apricorn_device` function searches for Apricorn USB devices with Vendor ID `0984`, retrieves their metadata, and returns a list of `WinUsbDeviceInfo` objects.

### Basic Usage
```python
from usb_tool import find_apricorn_device

device = find_apricorn_device()

if device:
    first_device = device[0]  # Access the first detected device
    print(first_device.idVendor)  # Correct attribute access
    print(first_device.idProduct)
    print(first_device.iSerial)
else:
    print("No Apricorn devices found.")
```

### Accessing Device Attributes
Each device returned is a `WinUsbDeviceInfo` `LinuxUsbDeviceInfo` or `macOSUsbDeviceInfo` object. Use **dot notation** to access properties:
```python
print(device.iManufacturer)  # Manufacturer Name
print(device.iProduct)       # Product Name
print(device.iSerial)        # Serial Number
print(device.usb_protocol)   # USB Version (e.g., USB 3.0)
print(device.usbController)  # Controller Type (Intel, ASMedia, etc.)
print(device.driveSize)      # Closest Matching Drive Size
```

### Finding a Specific Device by Serial Number
If you need a specific device from the list:
```python
serial_number = "116120005489"
device = find_apricorn_device()
for device in device:
    if device.iSerial == serial_number:
        print(f"Device Found: {device.iProduct} - Serial: {device.iSerial}")
        break
else:
    print("Device not found.")

```

## Development Notes

The source code is organised under the `usb_tool` package:

* `cross_usb.py` – command-line entry point and argument handling.
* `windows_usb.py`, `linux_usb.py`, `mac_usb.py` – platform specific device discovery and sorting logic.
* `utils.py` – shared helpers such as size conversion and USB version parsing.

All packaging metadata resides in `pyproject.toml` and the project can be installed in editable mode with `pip install -e .` for development.
