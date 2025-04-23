import platform
import cProfile
import pstats
import io
import re
import sys  # Import the sys module

def print_help():
    """
    Prints a detailed help message to the console.
    This simulates a 'man page' output.
    """

    help_text = """
usb-tool - Cross-platform USB tool for Apricorn devices

Description:
  The usb-tool is a command-line utility designed to identify and
  display information about Apricorn USB devices connected to your
  system. It supports Windows, macOS, and Linux platforms.

Usage:
  usb [options]

Options:
  -h, --help            Show this help message and exit.

Examples:
  usb                   List all connected Apricorn devices.
  usb -h                Show the manpage.
"""
    print(help_text)

def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print_help()
        sys.exit(0)  # Exit after displaying help

    if platform.system().lower().startswith("win"):
        from usb_tool import windows_usb
        devices = windows_usb.find_apricorn_device()
    elif platform.system().lower().startswith("darwin"):
        from usb_tool import mac_usb
        devices = mac_usb.find_apricorn_device()
    else:
        from usb_tool import linux_usb
        devices = linux_usb.find_apricorn_device()

    if not devices:
        print()
        print("No Apricorn devices found.")
    else:
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            for field_name, value in dev.__dict__.items():
                print(f"  {field_name}: {value}")
    print()

if __name__ == "__main__":
    if "-h" in sys.argv or "--help" in sys.argv:
        print_help()
    else:
        main()