import platform

def main():
    if platform.system().lower().startswith("win"):
        from usb_tool import windows_usb
        devices = windows_usb.find_apricorn_device()
    else:
        from usb_tool import linux_usb
        devices = linux_usb.find_apricorn_device()

    if not devices:
        print("No Apricorn devices found.")
    else:
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            for field_name, value in dev.__dict__.items():
                print(f"  {field_name}: {value}")
    print()
