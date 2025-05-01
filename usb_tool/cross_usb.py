# usb_tool/cross_usb.py

import platform
import sys
import argparse
import ctypes

# --- Platform check and conditional import ---
_SYSTEM = platform.system().lower()

if _SYSTEM.startswith("win"):
    try:
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
    # ... (keep as is) ...
    if not _SYSTEM.startswith("win"): return False
    try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError: return False
    except Exception: return False

# --- Helper Function Definition ---
def print_help():
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
  -h, --help                Show this help message and exit.
  -p, --poke DRIVE_NUMS     Windows Only: Send a SCSI READ(10) command ONLY to detected
                            Apricorn drives specified by their physical drive numbers
                            (comma-separated, e.g., '1' or '1,2'). Requires Admin rights.

Examples:
  usb_tool                  List all connected Apricorn devices.
  usb_tool --poke 1         Send a READ(10) command to detected Apricorn drive #1 (Windows Admin).
  usb_tool --poke 1,2       Send READ(10) commands to detected Apricorn drives #1 and #2
                            (Windows Admin).
  usb_tool -h               Show this help message.
"""
    print(help_text)

# --- Synchronous Helper for Poking ---
def sync_poke_drive(drive_num):
    if not POKE_AVAILABLE:
        print(f"  Drive {drive_num}: Poke SKIPPED (poke_device not available)")
        return False
    print(f"Poking drive {drive_num}...")
    try:
        read_data = send_scsi_read10(drive_num)
        return True
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


# --- Main Logic Function ---
def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="USB tool to find Apricorn devices. Can also 'poke' drives on Windows.",
        add_help=False
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show detailed help/manpage.")
    parser.add_argument(
        "-p", "--poke", type=str, metavar="DRIVE_NUMS",
        help="Windows only: Poke detected Apricorn drives by physical number (comma-separated)."
    )
    args = parser.parse_args()

    # --- Help Handling ---
    if args.help:
        print_help()
        sys.exit(0)

    # --- Perform Device Discovery EARLY if --poke is used ---
    devices = None
    if args.poke and _SYSTEM.startswith("win"): # Only need devices early for poke validation
        print("Scanning for Apricorn devices...")
        # Make sure to use the correct import based on package structure
        from . import windows_usb # Assuming running as package
        try:
            devices = windows_usb.find_apricorn_device()
            if not devices:
                print("No Apricorn devices found to poke.")
                # Exit here if no devices, prevents poke attempt later
                sys.exit(0 if not args.list else 1) # Exit cleanly if poke was the only arg
        except Exception as e:
            print(f"Error during initial device scan for poke validation: {e}", file=sys.stderr)
            sys.exit(1)


    # --- Poke Logic ---
    if args.poke:
        if not _SYSTEM.startswith("win"):
            print("Error: --poke option is only available on Windows.", file=sys.stderr)
            sys.exit(1)
        if not POKE_AVAILABLE:
            print("Error: Poke functionality could not be loaded.", file=sys.stderr)
            sys.exit(1)
        if not is_admin_windows():
            print("Error: --poke requires Administrator privileges.", file=sys.stderr)
            sys.exit(1)

        # Device scan should have happened above if devices is None or empty
        if devices is None: # Should not happen if logic above is correct, but safety check
            print("Error: Could not retrieve device list for validation.", file=sys.stderr)
            sys.exit(1)
        if not devices: # Check again in case scan yielded nothing
             print("No Apricorn devices found. Nothing to poke.", file=sys.stderr)
             sys.exit(0)


        # --- Validation Step ---
        valid_apricorn_drive_nums = set()
        for dev in devices:
            # Ensure the attribute exists and is a valid number (e.g., not -1)
            if hasattr(dev, 'physicalDriveNum') and isinstance(dev.physicalDriveNum, int) and dev.physicalDriveNum >= 0:
                valid_apricorn_drive_nums.add(dev.physicalDriveNum)

        if not valid_apricorn_drive_nums:
            print("Error: No Apricorn devices with valid physical drive numbers were detected.", file=sys.stderr)
            sys.exit(1)

        # Parse user input
        user_poke_nums_str = args.poke.split(',')
        user_poke_nums_int = set() # Use a set for efficient checking
        invalid_inputs = []
        try:
            for s in user_poke_nums_str:
                s_strip = s.strip()
                if not s_strip: continue
                num = int(s_strip)
                if num < 0:
                    raise ValueError("Drive number cannot be negative")
                user_poke_nums_int.add(num)
        except ValueError as e:
            invalid_inputs.append(s_strip if 's_strip' in locals() else s) # Capture the invalid string
            # Continue parsing others, report all invalid at once
            pass # Continue loop to find all format errors

        if invalid_inputs:
             print(f"Error: Invalid non-integer value(s) provided for --poke: {invalid_inputs}", file=sys.stderr)
             sys.exit(1)


        # Check which user numbers are valid Apricorn drives
        validated_poke_targets = []
        invalid_poke_targets = []
        for user_num in user_poke_nums_int:
            if user_num in valid_apricorn_drive_nums:
                validated_poke_targets.append(user_num)
            else:
                invalid_poke_targets.append(user_num)

        if invalid_poke_targets:
            print(f"usage: usb [-h] [-p DRIVE_NUMS]")
            print(f"usb: error: argument -p/--poke: invalid DRIVE_NUMS")
            sys.exit(1)

        if not validated_poke_targets:
             print("Error: No valid Apricorn drive numbers specified to poke.", file=sys.stderr)
             sys.exit(1)
        # --- End Validation Step ---


        # Proceed with poking ONLY the validated targets
        print()
        results = []
        for num in sorted(validated_poke_targets): # Poke in sorted order
            results.append(sync_poke_drive(num))

        if not all(results):
            print("Some poke operations failed.")
            # Consider exiting with error code if any poke fails
            # sys.exit(1)
        else:
            print()

    # --- List Logic ---
    # Run list if --list or no args given AND --poke wasn't the primary action
    elif args.list or not args.poke:
        # Only scan now if devices weren't already retrieved for poke validation
        if devices is None:
            print("Scanning for Apricorn devices...")
            # Make sure to use the correct import based on package structure
            if _SYSTEM.startswith("win"): from . import windows_usb as os_usb
            elif _SYSTEM.startswith("darwin"): from . import mac_usb as os_usb
            elif _SYSTEM.startswith("linux"): from . import linux_usb as os_usb
            else:
                print(f"Unsupported platform: {_SYSTEM}", file=sys.stderr)
                sys.exit(1)
            try:
                devices = os_usb.find_apricorn_device()
            except Exception as e:
                 print(f"Error during device scan: {e}", file=sys.stderr)
                 sys.exit(1)


        if not devices:
            print("\nNo Apricorn devices found.\n")
        else:
            for idx, dev in enumerate(devices, start=1):
                # Use original title format
                print(f"\n=== Apricorn Device #{idx} ===")
                try: attributes = vars(dev)
                except TypeError: attributes = dev if isinstance(dev, dict) else {}

                if attributes:
                    for field_name, value in attributes.items():
                        # Use original field: value format (no padding)
                        print(f"  {field_name}: {value}")
                else:
                     print(f"  Device Info: {dev}") # Fallback if vars() fails
            print() # Keep the final newline for spacing

# --- Entry Point for direct execution ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)