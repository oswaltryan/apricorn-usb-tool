# usb_tool/cross_usb.py

import platform
import sys
import argparse
import asyncio
import ctypes

# --- Platform check and conditional import ---
_SYSTEM = platform.system().lower() # Store for easier use

if _SYSTEM.startswith("win"):
    try:
        # Use absolute import assuming poke_device is in the same directory
        # If running as a package, use: from .poke_device import ...
        from .poke_device import send_scsi_read10, ScsiError
        POKE_AVAILABLE = True
    except ImportError:
        print("Warning: Could not import poke_device module.", file=sys.stderr)
        POKE_AVAILABLE = False
    except Exception as e:
        print(f"Warning: Error importing poke_device: {e}", file=sys.stderr)
        POKE_AVAILABLE = False
else:
    POKE_AVAILABLE = False

# --- Helper for Admin Check ---
def is_admin_windows():
    """Check for admin privileges on Windows."""
    if not _SYSTEM.startswith("win"): # Only relevant on Windows
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        return False
    except Exception:
        return False

# --- Helper Function Definition (Moved Here) ---
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
  system. It supports Windows, macOS, and Linux platforms. It can also
  send a basic SCSI command ('poke') to specified drives on Windows.

Usage:
  usb_tool [options]  # Or how you intend to invoke it

Options:
  -h, --help            Show this help message and exit.
  --list                List connected Apricorn devices (this is the default action).
  --poke DRIVE_NUMS     Windows Only: Send a SCSI READ(10) command to one or
                        more physical drive numbers (comma-separated, e.g., '1'
                        or '1,2') to trigger activity LED. Requires Admin rights.

Examples:
  usb_tool                   List all connected Apricorn devices.
  usb_tool --list            Explicitly list devices.
  usb_tool --poke 1          Send a READ(10) command to PhysicalDrive1 (Windows Admin).
  usb_tool --poke 1,2        Send READ(10) commands concurrently to PhysicalDrive1
                             and PhysicalDrive2 (Windows Admin).
  usb_tool -h                Show this help message.
"""
    print(help_text)

# --- Async Helper for Poking ---
async def async_poke_drive(drive_num):
    """Async wrapper to call send_scsi_read10 and handle results."""
    # Check availability again inside the task (optional but safer)
    if not POKE_AVAILABLE:
        print(f"  Drive {drive_num}: Poke SKIPPED (poke_device not available)")
        return False

    print(f"Poking drive {drive_num}...")
    try:
        read_data = await asyncio.to_thread(send_scsi_read10, drive_num)
        print(f"  Drive {drive_num}: Poke SUCCESS (Read {len(read_data)} bytes)")
        return True
    # Make sure ScsiError is defined if POKE_AVAILABLE is True
    except ScsiError as e:
        print(f"  Drive {drive_num}: Poke FAILED (SCSI Error)")
        print(f"    Status: 0x{e.scsi_status:02X}, Sense: {e.sense_hex}")
        return False
    except PermissionError as e:
        print(f"  Drive {drive_num}: Poke FAILED (PermissionError - Run as Admin)")
        print(f"    Details: {e}")
        return False
    except OSError as e:
        print(f"  Drive {drive_num}: Poke FAILED (OSError - Drive valid?)")
        print(f"    Details: {e}")
        return False
    except ValueError as e:
         print(f"  Drive {drive_num}: Poke FAILED (ValueError)")
         print(f"    Details: {e}")
         return False
    except Exception as e:
        print(f"  Drive {drive_num}: Poke FAILED (Unexpected Error)")
        print(f"    Details: {e}")
        return False

# --- Main Function (Now Async) ---
async def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="USB tool to find Apricorn devices. Can also 'poke' drives on Windows.",
        add_help=False # Disable default help to handle it manually below
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="Show detailed help/manpage."
    )
    parser.add_argument(
        "--poke", type=str, metavar="DRIVE_NUMS",
        help="Windows only: Send a READ(10) command to one or more physical drive numbers "
             "(comma-separated, e.g., '1' or '1,2'). Requires Admin privileges."
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List connected Apricorn devices (default action)."
    )

    args = parser.parse_args()

    # --- Help Handling ---
    if args.help:
        print_help() # Now defined before call
        sys.exit(0)

    # --- Poke Logic ---
    if args.poke:
        if not _SYSTEM.startswith("win"):
            print("Error: --poke option is only available on Windows.", file=sys.stderr)
            sys.exit(1)

        if not POKE_AVAILABLE:
            print("Error: Poke functionality could not be loaded (poke_device import failed).", file=sys.stderr)
            sys.exit(1)

        if not is_admin_windows():
            print("Error: --poke requires Administrator privileges.", file=sys.stderr)
            sys.exit(1)

        drive_nums_str = args.poke.split(',')
        drive_nums_int = []
        invalid_num_str = None # Keep track of the invalid string
        try:
            for s in drive_nums_str:
                s_strip = s.strip()
                if not s_strip: continue # Skip empty strings from extra commas
                invalid_num_str = s_strip # Store the current one in case of error
                num = int(s_strip)
                if num < 0:
                    raise ValueError("Drive number cannot be negative")
                drive_nums_int.append(num)
        except ValueError as e:
            print(f"Error: Invalid drive number specified in --poke argument: '{invalid_num_str}'. Must be an integer. {e}", file=sys.stderr)
            sys.exit(1)

        if not drive_nums_int:
            print("Error: No valid drive numbers provided for --poke.", file=sys.stderr)
            sys.exit(1)

        print(f"Attempting to concurrently poke drives: {drive_nums_int}")
        tasks = [async_poke_drive(num) for num in drive_nums_int]
        results = await asyncio.gather(*tasks)

        if all(results):
            print("All poke operations completed successfully.")
        else:
            print("Some poke operations failed.")
            # sys.exit(1) # Exit with error if any fail

    # --- List Logic (Default or explicit --list) ---
    # Run list if --list or no args given *and* --poke wasn't used
    elif args.list or not args.poke:
        devices = None
        print("Scanning for Apricorn devices...")
        if _SYSTEM.startswith("win"):
            # Use absolute import assuming it's runnable directly or in path
            # If running as package: from . import windows_usb
            import windows_usb
            devices = windows_usb.find_apricorn_device()
        elif _SYSTEM.startswith("darwin"):
            # Use absolute import assuming it's runnable directly or in path
            # If running as package: from . import mac_usb
            import mac_usb
            devices = mac_usb.find_apricorn_device()
        elif _SYSTEM.startswith("linux"):
            # Use absolute import assuming it's runnable directly or in path
            # If running as package: from . import linux_usb
            import linux_usb
            devices = linux_usb.find_apricorn_device()
        else:
             print(f"Unsupported platform: {_SYSTEM}", file=sys.stderr)
             sys.exit(1)


        if not devices:
            print("\nNo Apricorn devices found.\n")
        else:
            for idx, dev in enumerate(devices, start=1):
                print(f"\n=== Apricorn Device #{idx} ===")
                try:
                    # Use vars() if dev is a dataclass or object with __dict__
                    attributes = vars(dev)
                except TypeError:
                    # Fallback if vars() doesn't work (e.g., it's a dict already)
                    attributes = dev if isinstance(dev, dict) else {}

                if attributes:
                    for field_name, value in attributes.items():
                        print(f"  {field_name}: {value}")
                else:
                     print(f"  Device Info: {dev}") # Print raw object if vars fails
            print()
    else:
        # Should not be reachable if logic is correct, but as a fallback
        parser.print_usage()
        print("Use -h or --help for more details.")

def cli_entry_point():
    """
    Synchronous entry point for the command-line interface.
    Runs the main async function using asyncio.run().
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        # Optional: exit with a specific code for interruption
        sys.exit(130) # Standard code for Ctrl+C termination
    except Exception as e:
        # Optionally catch other top-level errors if needed, though
        # main() should ideally handle its specific exceptions.
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

# --- Entry Point ---
if __name__ == "__main__":
    # Use asyncio.run() to execute the async main function
    try:
        # asyncio.run(main())
        cli_entry_point()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)

# Note: The print_help() function definition is now ABOVE main()