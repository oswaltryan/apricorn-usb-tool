import ctypes

def get_serial_number(dev, iSerialNumber):
    # Allocate a buffer for the serial number string
    buffer = ctypes.create_string_buffer(256)
    # Call the libusb function to get the string descriptor (the exact call might differ based on your binding)
    rc = usb.get_string_descriptor_ascii(dev, iSerialNumber, buffer, ctypes.sizeof(buffer))
    if rc > 0:
        return buffer.value.decode('utf-8')
    else:
        return None

# Usage example:
serial_str = get_serial_number(dev, desc.iSerialNumber)
print("Serial Number:", serial_str)