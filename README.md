

## Overview
This documentation provides instructions on how to install our Apricorn device USB library and use the `find_apricorn_device` function to detect, enumerate, and interact with Apricorn USB devices using **libusb** and **WMI**.

## Prerequisites
Ensure you have Python 3.12 installed.

### 1. (Optional) Create a Virtual Environment
```sh
python3.12 -m venv venv
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

### 2. Install Dependencies
To ensure compatibility, install dependencies from `requirements.txt`:
```sh
pip install -r requirements.txt
```

### 3. Install Dependencies from Local Wheel Files (Offline Mode)
If installing in an environment without internet access:
```sh
pip install --no-index --find-links=wheels -r requirements.txt
```

### 4. Install as a Module for Global Access
For global installation:
```sh
pip install .
```

### 5. Install Globally as a Module (Offline Mode)
```sh
pip install --no-index --find-links=wheels .
```

### 6. Invoke the USB Detection Script
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
from windows_usb import find_apricorn_device

devices = find_apricorn_device()

if devices:
    first_device = devices[0]  # Access the first detected device
    print(first_device.idVendor)  # Correct attribute access
    print(first_device.idProduct)
    print(first_device.iSerial)
else:
    print("No Apricorn devices found.")
```

### Accessing Device Attributes
Each device returned is a `WinUsbDeviceInfo` object. Use **dot notation** to access properties:
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

for device in devices:
    if device.iSerial == serial_number:
        print(f"Device Found: {device.iProduct} - Serial: {device.iSerial}")
        break
else:
    print("Device not found.")

```
