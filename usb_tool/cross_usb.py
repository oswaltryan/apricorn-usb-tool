import platform
import sys
import argparse  # Import the argparse module


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
    parser = argparse.ArgumentParser(
        description="USB tool to find Apricorn devices"
    )
    # parser.add_argument(  # Removed: Let argparse handle -h/--help
    #     "-h", "--help", action="store_true", help="Show this help message and exit"
    # )

    args = parser.parse_args()

    if len(sys.argv) > 1 and not (sys.argv[1] in ('-h', '--help')):
        print_help()
        sys.exit(0)

    if len(sys.argv) == 1 or args.list:  # Default action if no args or -list
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
            print("\nNo Apricorn devices found.\n")
        else:
            for idx, dev in enumerate(devices, start=1):
                print(f"\n=== Apricorn Device #{idx} ===")
                for field_name, value in dev.__dict__.items():
                    print(f"  {field_name}: {value}")
            print()


if __name__ == "__main__":
    main()