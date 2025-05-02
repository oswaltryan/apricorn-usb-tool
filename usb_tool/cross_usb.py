# usb_tool/cross_usb.py

import platform
import sys
import argparse
import ctypes

# --- Platform check and conditional import ---
_SYSTEM = platform.system().lower()

if _SYSTEM.startswith("win"):
    try:
        # Use relative import for package structure
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
  usb_tool [options]

Options:
  -h, --help                Show this help message and exit.
  -p, --poke DRIVE_NUMS     Windows Only: Send a SCSI READ(10) command ONLY to detected
                            Apricorn drives specified by their physical drive numbers
                            (comma-separated, e.g., '1' or '1,2') OR use 'all'
                            to poke all detected Apricorn drives. Skips devices
                            detected in OOB mode. Requires Admin rights.

Examples:
  usb_tool                  List all connected Apricorn devices (default action).
  usb_tool -p 1             Send READ(10) command to detected Apricorn drive #1 (Windows Admin).
  usb_tool -p 1,2           Send READ(10) commands to detected Apricorn drives #1 and #2 (Windows Admin).
  usb_tool -p all           Send READ(10) commands to ALL detected, non-OOB Apricorn drives (Windows Admin).
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
        description="USB tool for Apricorn devices.",
        add_help=False
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show detailed help/manpage.")
    parser.add_argument(
        "-p", "--poke", type=str, metavar="DRIVE_NUMS",
        help="Windows only: Poke detected Apricorn drives by physical number (comma-separated) or use 'all'."
    )
    args = parser.parse_args()

    # --- Help Handling ---
    if args.help:
        print_help()
        sys.exit(0)

    # --- Device Discovery ---
    devices = None
    scan_error = False
    scan_needed = (_SYSTEM.startswith("win") and args.poke) or (not args.poke)

    if scan_needed:
        print("Scanning for Apricorn devices...")
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
             scan_error = True

    # --- Action Logic ---
    # Poke Action
    if args.poke:
        # Perform initial checks
        if not _SYSTEM.startswith("win"):
            parser.error("--poke option is only available on Windows.")
        if not POKE_AVAILABLE:
            parser.error("Poke functionality could not be loaded.")
        if not is_admin_windows():
            parser.error("--poke requires Administrator privileges.")
        if scan_error:
             parser.error("Cannot execute --poke due to previous device scan error.")
        if devices is None:
             parser.error("Device scan failed or yielded no results; cannot validate poke targets.")
        if not devices:
             print("No Apricorn devices found. Nothing to poke.")
             sys.exit(0)

        # --- Enhanced Validation Step (Including OOB Check) ---
        all_detected_drive_nums = set()
        pokeable_drive_nums = set()
        oob_drive_nums = set()

        for dev in devices:
            p_num = getattr(dev, 'physicalDriveNum', -1)
            if isinstance(p_num, int) and p_num >= 0:
                all_detected_drive_nums.add(p_num)
                oob_status = getattr(dev, 'driveSizeGB', None) == "N/A (OOB Mode)"
                if oob_status:
                    oob_drive_nums.add(p_num)
                else:
                    pokeable_drive_nums.add(p_num)

        if not all_detected_drive_nums:
             parser.error("No Apricorn devices with valid physical drive numbers were detected.")
        # --- End Enhanced Validation Step Preparation ---

        # --- Determine Poke Targets ('all' or specific numbers) ---
        poke_input = args.poke.strip()
        user_target_nums = set()
        validated_poke_targets = [] # Final list to actually poke
        skipped_oob_targets = []    # Numbers explicitly requested but skipped due to OOB
        invalid_targets = []        # Numbers requested but not detected/invalid pNum

        if poke_input.lower() == 'all':
            # In 'all' mode, we target all pokeable drives
            user_target_nums = pokeable_drive_nums # This is the set we want to poke
            # Identify which OOB devices are implicitly skipped when 'all' is used
            skipped_oob_targets = list(oob_drive_nums) # All OOB devices are skipped
            validated_poke_targets = list(pokeable_drive_nums)

        else:
            # Parse specific numbers requested by the user
            user_poke_nums_str_list = poke_input.split(',')
            invalid_inputs = []
            processed_any_valid_element = False
            for s in user_poke_nums_str_list:
                s_strip = s.strip()
                if not s_strip: continue
                processed_any_valid_element = True
                try:
                    if s_strip.lower() == 'all':
                        invalid_inputs.append(s_strip + " ('all' keyword cannot be mixed)")
                        continue
                    num = int(s_strip)
                    if num < 0: invalid_inputs.append(s_strip + " (negative)")
                    else: user_target_nums.add(num) # Collect all numbers user typed
                except ValueError: invalid_inputs.append(s_strip)

            # Report parsing errors
            if invalid_inputs:
                 parser.error(f"Invalid value(s) for --poke: {invalid_inputs}. Use comma-separated non-negative integers or 'all'.")
            if not processed_any_valid_element:
                 parser.error("No drive numbers provided for --poke argument.")
            if processed_any_valid_element and not user_target_nums:
                 parser.error(f"No valid positive integers found in --poke argument '{args.poke}'.")

            # --- Validate the user_target_nums ---
            for num in user_target_nums:
                if num in pokeable_drive_nums:
                    validated_poke_targets.append(num)
                elif num in oob_drive_nums:
                    # It's an OOB device the user explicitly asked for
                    skipped_oob_targets.append(num)
                else:
                    # It's a number the user asked for but isn't a detected Apricorn drive
                    invalid_targets.append(num)

            if invalid_targets:
                 error_msg = (f"argument -p/--poke: Invalid or non-Apricorn drive number(s) specified. "
                              f"Detected Apricorn drives (by number): {sorted(list(all_detected_drive_nums))}. "
                              f"Invalid specified: {sorted(invalid_targets)}.")
                 parser.error(error_msg)


        # --- Unified Reporting and Final Check ---
        # Check if any valid targets remain *after* potential skipping
        if not validated_poke_targets:
             # This covers the case where 'all' was used but all drives were OOB,
             # OR specific numbers were requested but they were all either OOB or invalid.
             print()
             parser.error(f"No valid Apricorn drive numbers specified to poke {sorted(skipped_oob_targets)}")
             sys.exit(1)
        # --- End Final Validation ---

        # --- Proceed with Poking ---
        print()
        results = []
        all_success = True
        for num in sorted(validated_poke_targets):
            success = sync_poke_drive(num)
            results.append(success)
            if not success:
                 all_success = False

        # Removed separator print
        if not all_success:
            print("Some poke operations failed.")
            sys.exit(1)
        else:
            print()

        # Report skipped OOB devices (if any) - SAME message for both 'all' and specific numbers
        if skipped_oob_targets:
            parser.error(f"Skipping poke for OOB Mode devices: {sorted(skipped_oob_targets)}") # Consistent message

    # List Action (Default if poke not specified)
    else:
        # --- (Keep existing list logic and printing) ---
        if scan_error:
            print("Cannot list devices due to previous scan error.", file=sys.stderr)
            sys.exit(1)
        if devices is None:
            print("Device scan failed or yielded no results.", file=sys.stderr)
            sys.exit(1)
        if not devices:
            print("\nNo Apricorn devices found.\n")
        else:
            for idx, dev in enumerate(devices, start=1):
                print(f"\n=== Apricorn Device #{idx} ===")
                try: attributes = vars(dev)
                except TypeError: attributes = dev if isinstance(dev, dict) else {}
                if attributes:
                    for field_name, value in attributes.items():
                        print(f"  {field_name}: {value}")
                else:
                     print(f"  Device Info: {dev}")
            print()

# --- Entry Point for direct execution ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)