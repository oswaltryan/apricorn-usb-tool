# usb_tool/cross_usb.py

import platform
import sys
import argparse
import ctypes
import os # For path validation on Linux

# --- Platform check and conditional import ---
_SYSTEM = platform.system().lower()

if _SYSTEM.startswith("win") or _SYSTEM.startswith("linux") or _SYSTEM.startswith("darwin"):
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

# --- Helper for Admin Check (Windows Only) ---
def is_admin_windows():
    if not _SYSTEM.startswith("win"): return False
    try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError: return False
    except Exception: return False

# --- Helper Function Definition ---
def print_help():
    if _SYSTEM.startswith("win"):
        help_text = """
NAME
       usb - Cross-platform USB tool for Apricorn devices
       usb-update - Update the usb-tool installation (if installed from Git)

SYNOPSIS
       usb [-h] [-p TARGETS]
       usb-update

DESCRIPTION
       The usb-tool utility scans the system for connected Apricorn USB devices
       (Vendor ID 0984) using WMI and libusb (if available) and displays detailed
       information about them. It can also send a basic SCSI READ(10) command
       (poke) to specified devices using the SCSI Pass Through Interface.

       The poke operation requires Administrator privileges.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected Apricorn
              drives. TARGETS should be a comma-separated list of physical
              drive numbers (e.g., '1', '0,2' - corresponding to \\.\PhysicalDriveX)
              or the keyword 'all' to target all detected, non-OOB Apricorn drives.
              This operation requires Administrator privileges.
              Devices detected in Out-Of-Box (OOB) mode (reporting size as N/A)
              will be skipped.

DEFAULT BEHAVIOR
       If run without options, `usb` scans for Apricorn devices and prints
       detailed information for each one found, including:
       VID/PID, Serial Number, Product Name, Manufacturer, USB Version (bcdUSB),
       Device Revision (bcdDevice), Drive Size (or N/A), UAS/SCSI status,
       USB Controller type (e.g., Intel, ASMedia), Bus/Device Address, and
       Physical Drive Number.

USB-UPDATE COMMAND
       The `usb-update` command attempts to update the tool if it was installed
       in editable mode from a Git repository. It runs `git pull origin main`
       and then `pip install --upgrade .`.

PRIVILEGES
       - Listing devices (`usb`): Generally works as a standard user.
       - Poking devices (`usb -p`): Requires Administrator privileges to access
         physical drives via the SCSI Pass Through IOCTL. Run from an
         Administrator command prompt or PowerShell.
       - Updating (`usb-update`): May require Administrator privileges if installed
         globally.

EXAMPLES
       usb
              List all detected Apricorn devices.

       usb -p 1
              (Run as Admin) Send a SCSI READ(10) command to the Apricorn device
              identified as PhysicalDrive1.

       usb -p 0,2
              (Run as Admin) Send a SCSI READ(10) command to devices
              PhysicalDrive0 and PhysicalDrive2.

       usb -p all
              (Run as Admin) Send a SCSI READ(10) command to all detected,
              non-OOB Apricorn devices.

       usb-update
              Attempt to update the tool from the Git repository.
"""
    elif _SYSTEM.startswith("linux"):
        help_text = """
NAME
       usb - Cross-platform USB tool for Apricorn devices
       usb-update - Update the usb-tool installation (if installed from Git)

SYNOPSIS
       usb [-h] [-p TARGETS]
       usb-update

DESCRIPTION
       The usb-tool utility scans the system for connected Apricorn USB devices
       (Vendor ID 0984) and displays detailed information about them. It can
       also send a basic SCSI READ(10) command (poke) to specified devices.

       On Linux, full device scanning details (e.g., via lshw, fdisk, lsusb -v)
       may require root privileges. The poke operation requires root privileges
       to access block devices directly.

       An optional script (`update_sudoersd.sh`) can be run with sudo to
       configure passwordless sudo access for specific scanning commands (`lshw`,
       `fdisk`), potentially allowing `usb` (without poke) to show more details
       without running the main tool as root.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected Apricorn
              drives. TARGETS should be a comma-separated list of block device
              paths (e.g., '/dev/sda', '/dev/sda,/dev/sdb') or the keyword
              'all' to target all detected, non-OOB Apricorn drives.
              This operation requires root privileges (e.g., run via `sudo usb -p ...`).
              Devices detected in Out-Of-Box (OOB) mode (reporting size as N/A)
              will be skipped.

DEFAULT BEHAVIOR
       If run without options, `usb` scans for Apricorn devices and prints
       detailed information for each one found, including:
       VID/PID, Serial Number, Product Name, Manufacturer, USB Version (bcdUSB),
       Device Revision (bcdDevice), Drive Size (or N/A), UAS/SCSI status,
       and Block Device path (e.g., /dev/sda).

USB-UPDATE COMMAND
       The `usb-update` command attempts to update the tool if it was installed
       in editable mode from a Git repository. It runs `git pull origin main`
       and then `pip install --upgrade .`. It may require root privileges
       depending on the installation location.

PRIVILEGES
       - Listing devices (`usb`): May provide more detail if run as root or if
         the `sudoers.d` configuration is applied (using
         `update_sudoersd.sh`). Basic listing may work as a regular user.
       - Poking devices (`usb -p`): Requires root privileges to access block
         devices via the ioctl interface. Use `sudo`.
       - Updating (`usb-update`): May require root privileges if installed
         globally.

EXAMPLES
       usb
              List all detected Apricorn devices.

       sudo usb -p /dev/sdb
              Send a SCSI READ(10) command to the Apricorn device at /dev/sdb.

       sudo usb -p /dev/sda,/dev/sdc
              Send a SCSI READ(10) command to devices /dev/sda and /dev/sdc.

       sudo usb -p all
              Send a SCSI READ(10) command to all detected, non-OOB Apricorn devices.

       usb-update
              Attempt to update the tool from the Git repository.

       sudo ./update_sudoersd.sh
              (Run from source directory) Install the sudoers configuration to
              allow passwordless execution of specific scanning commands for the
              `usb` tool when run by any user via sudo.
"""
    print(help_text)

# --- Synchronous Helper for Poking ---
def sync_poke_drive(device_identifier):
    """
    Wrapper to call send_scsi_read10 and print status messages.
    device_identifier: int for Windows drive number, str for Linux path.
    """
    if not POKE_AVAILABLE:
        print(f"  Device {device_identifier}: Poke SKIPPED (poke_device not available)")
        return False
    print(f"Poking device {device_identifier}...")
    try:
        # Call the cross-platform function
        read_data = send_scsi_read10(device_identifier)
        # If successful, the function returns data, but we just need success status here
        # Mimic Windows output format
        # print(f"  Device {device_identifier}: Poke SUCCEEDED.") # Success message handled by caller loop
        return True
    except ScsiError as e:
        # Mimic Windows output format
        print(f"  Device {device_identifier}: Poke FAILED (SCSI Error)")
        print(f"    Status: 0x{e.scsi_status:02X}, Sense: {e.sense_hex}")
        return False
    except PermissionError as e:
        # Mimic Windows output format (adjusting message slightly)
        privilege = "Admin (Windows)" if _SYSTEM.startswith("win") else "root (Linux)"
        print(f"  Device {device_identifier}: Poke FAILED (PermissionError - Run as {privilege})")
        print(f"    Details: {e}")
        return False
    except FileNotFoundError as e: # Specific error for Linux/macOS paths
        print(f"  Device {device_identifier}: Poke FAILED (FileNotFoundError - Path valid?)")
        print(f"    Details: {e}")
        return False
    except OSError as e:
        # General OS error, could be invalid handle/fd, device not ready, etc.
        # Mimic Windows output format
        err_type = "Drive valid?" if _SYSTEM.startswith("win") else "Device valid/ready?"
        print(f"  Device {device_identifier}: Poke FAILED (OSError - {err_type})")
        print(f"    Details: {e}")
        return False
    except ValueError as e: # e.g., invalid input to send_scsi_read10
         print(f"  Device {device_identifier}: Poke FAILED (ValueError)")
         print(f"    Details: {e}")
         return False
    except NotImplementedError as e: # If poke isn't supported on this OS
         print(f"  Device {device_identifier}: Poke FAILED (NotImplementedError)")
         print(f"    Details: {e}")
         return False
    except Exception as e:
        # Catch-all for unexpected issues
        print(f"  Device {device_identifier}: Poke FAILED (Unexpected Error)")
        print(f"    Details: {e}")
        return False

# --- Main Logic Function ---
def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="USB tool for Apricorn devices.",
        add_help=False # Use custom help print_help()
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show detailed help/manpage.")
    # Updated help text for TARGETS based on platform
    poke_help = ("Windows: Poke detected Apricorn drives by physical number (comma-separated) or 'all'. "
                 "Linux: Poke by block device path (comma-separated, e.g., /dev/sda) or 'all'. "
                 "Requires Admin/root.")
    parser.add_argument(
        "-p", "--poke", type=str, metavar="TARGETS",
        help=poke_help
    )
    args = parser.parse_args()

    # --- Help Handling ---
    if args.help:
        print_help() # Call the updated function
        sys.exit(0)

    # --- Device Discovery ---
    devices = None
    scan_error = False
    scan_needed = True # Always scan if poke or list is intended

    # Dynamically import the correct OS module
    os_usb = None
    if _SYSTEM.startswith("win"):
        from . import windows_usb as os_usb
    elif _SYSTEM.startswith("darwin"):
        # Poke not supported on Darwin currently, but listing is
        from . import mac_usb as os_usb
    elif _SYSTEM.startswith("linux"):
        from . import linux_usb as os_usb
    else:
        print(f"Unsupported platform: {_SYSTEM}", file=sys.stderr)
        sys.exit(1)

    print("Scanning for Apricorn devices...")
    try:
        devices = os_usb.find_apricorn_device()
    except Exception as e:
         print(f"Error during device scan: {e}", file=sys.stderr)
         # Optionally print traceback for debugging
         # import traceback
         # traceback.print_exc()
         scan_error = True

    # --- Action Logic ---
    # Poke Action
    if args.poke:
        # --- Initial Checks ---
        if not (_SYSTEM.startswith("win") or _SYSTEM.startswith("linux")):
            parser.error(f"--poke option is only available on Windows and Linux (current: {_SYSTEM}).")
        if not POKE_AVAILABLE:
            parser.error("Poke functionality could not be loaded (poke_device import failed).")

        # Privilege check / info message
        if _SYSTEM.startswith("win"):
            if not is_admin_windows():
                parser.error("--poke requires Administrator privileges on Windows.")
        elif _SYSTEM.startswith("linux"):
             # Check effective UID. If not 0 (root), print warning and proceed.
             # The actual permission error will be caught during device open/ioctl.
             try:
                 if os.geteuid() != 0:
                     print("\nWarning: --poke on Linux typically requires root privileges (use sudo).")
             except AttributeError:
                  print("\nWarning: Cannot determine user privileges. --poke on Linux typically requires root.")


        if scan_error:
             parser.error("Cannot execute --poke due to previous device scan error.")
        if devices is None:
             # Check if scan *attempted* but failed vs never ran
             if scan_needed:
                 parser.error("Device scan failed or yielded no results; cannot validate poke targets.")
             else:
                 # This case shouldn't happen if scan_needed=True always
                 parser.error("Device scan did not run; cannot validate poke targets.")
        if not devices:
             print("No Apricorn devices found. Nothing to poke.")
             sys.exit(0)

        # --- Enhanced Validation Step (Platform Aware) ---
        # Map device identifier (drive num or path) to the device object
        # Also track OOB status based on the identifier
        detected_pokeable_map = {} # {identifier: device_obj} for non-OOB
        detected_oob_map = {}      # {identifier: device_obj} for OOB

        for dev in devices:
            identifier = None
            is_oob = False
            try:
                # Check for OOB - use startswith("N/A") for flexibility
                size_attr = getattr(dev, 'driveSizeGB', 'Unknown')
                # Convert to string to check, handles int size values too
                if str(size_attr).strip().upper().startswith("N/A"):
                     is_oob = True

                if _SYSTEM.startswith("win"):
                    p_num = getattr(dev, 'physicalDriveNum', -1)
                    if isinstance(p_num, int) and p_num >= 0:
                        identifier = p_num
                elif _SYSTEM.startswith("linux"):
                    b_dev = getattr(dev, 'blockDevice', '')
                    # Ensure it looks like a valid block device path
                    if isinstance(b_dev, str) and b_dev.startswith('/dev/'):
                        identifier = b_dev

                if identifier is not None:
                    if is_oob:
                        detected_oob_map[identifier] = dev
                    else:
                        detected_pokeable_map[identifier] = dev

            except Exception as e:
                 print(f"Warning: Error processing device data during validation: {dev} - {e}", file=sys.stderr)
                 continue # Skip this device if critical data is missing/malformed

        all_detected_identifiers = set(detected_pokeable_map.keys()) | set(detected_oob_map.keys())

        if not all_detected_identifiers:
             parser.error("No Apricorn devices with valid identifiers (drive number/path) were detected.")
        # --- End Enhanced Validation Step Preparation ---

        # --- Determine Poke Targets ('all' or specific identifiers) ---
        poke_input = args.poke.strip()
        user_target_identifiers = set() # Identifiers user requested (int or str)
        validated_poke_targets = [] # Final list of identifiers to actually poke
        skipped_oob_targets = []    # Identifiers explicitly requested but skipped due to OOB
        invalid_targets = []        # Identifiers requested but not detected/invalid

        if poke_input.lower() == 'all':
            # In 'all' mode, we target all *pokeable* drives found
            user_target_identifiers = set(detected_pokeable_map.keys()) # This is the set we want to poke
            # Identify which OOB devices are implicitly skipped when 'all' is used
            skipped_oob_targets = list(detected_oob_map.keys()) # All OOB devices are skipped
            validated_poke_targets = list(detected_pokeable_map.keys())

        else:
            # Parse specific identifiers requested by the user
            user_poke_input_list = poke_input.split(',')
            invalid_inputs_reported = [] # Store specific invalid strings for error message
            processed_any_valid_element = False # Track if we got any non-empty string

            for s in user_poke_input_list:
                s_strip = s.strip()
                if not s_strip: continue # Skip empty parts from double commas etc.

                processed_any_valid_element = True

                # Block mixing 'all' with specific identifiers
                if s_strip.lower() == 'all':
                     invalid_inputs_reported.append(s_strip + " ('all' keyword cannot be mixed)")
                     continue

                # Try to parse based on OS
                target_id = None
                is_valid_format = False
                if _SYSTEM.startswith("win"):
                     try:
                         num = int(s_strip)
                         if num >= 0:
                             target_id = num
                             is_valid_format = True
                         else:
                             invalid_inputs_reported.append(s_strip + " (negative number)")
                     except ValueError:
                         invalid_inputs_reported.append(s_strip + " (not a valid number)")
                elif _SYSTEM.startswith("linux"):
                     # Basic check: must start with /dev/
                     if s_strip.startswith('/dev/'):
                         target_id = s_strip
                         is_valid_format = True
                     else:
                         invalid_inputs_reported.append(s_strip + " (not a valid /dev/ path)")

                if is_valid_format and target_id is not None:
                     user_target_identifiers.add(target_id)
                # else: error already reported

            # Report parsing errors
            if invalid_inputs_reported:
                 error_msg_parts = ["Invalid value(s) for --poke:"]
                 error_msg_parts.extend(invalid_inputs_reported)
                 if _SYSTEM.startswith("win"):
                     error_msg_parts.append("Use comma-separated non-negative integers or 'all'.")
                 elif _SYSTEM.startswith("linux"):
                     error_msg_parts.append("Use comma-separated /dev/ paths or 'all'.")
                 parser.error(" ".join(error_msg_parts))

            if not processed_any_valid_element:
                 parser.error("No device identifiers provided for --poke argument.")
            # If we processed inputs but ended up with no valid identifiers
            if processed_any_valid_element and not user_target_identifiers:
                 err_type = "positive integers" if _SYSTEM.startswith("win") else "/dev/ paths"
                 parser.error(f"No valid {err_type} found in --poke argument '{args.poke}'.")

            # --- Validate the user_target_identifiers against detected devices ---
            for identifier in user_target_identifiers:
                if identifier in detected_pokeable_map:
                    validated_poke_targets.append(identifier)
                elif identifier in detected_oob_map:
                    # It's an OOB device the user explicitly asked for
                    skipped_oob_targets.append(identifier)
                else:
                    # It's an identifier the user asked for but isn't a detected Apricorn drive
                    invalid_targets.append(identifier)

            if invalid_targets:
                 id_type = "drive number(s)" if _SYSTEM.startswith("win") else "device path(s)"
                 error_msg = (f"argument -p/--poke: Invalid or non-Apricorn {id_type} specified. "
                              f"Detected Apricorn identifiers: {sorted(list(all_detected_identifiers))}. "
                              f"Invalid specified: {sorted(invalid_targets)}.")
                 parser.error(error_msg)


        # --- Unified Reporting and Final Check ---
        # Check if any valid targets remain *after* potential skipping
        if not validated_poke_targets:
             # This covers cases where 'all' found only OOB, or specific targets were all OOB/invalid.
             skipped_msg = f" Skipped OOB devices: {sorted(skipped_oob_targets)}." if skipped_oob_targets else ""
             parser.error(f"No valid, non-OOB Apricorn devices specified or found to poke.{skipped_msg}")
             # sys.exit(1) # parser.error already exits

        # Report skipped OOB devices (if any) - Consistent message
        if skipped_oob_targets:
             print(f"Info: Skipping poke for OOB Mode devices: {sorted(skipped_oob_targets)}") # Use print for info/warning


        # --- Proceed with Poking ---
        print() # Separator before poking starts
        results = []
        all_success = True
        # Sort identifiers for consistent execution order
        for identifier in sorted(validated_poke_targets, key=lambda x: str(x)):
            success = sync_poke_drive(identifier)
            results.append(success)
            if not success:
                 all_success = False

        # Report overall status
        print() # Separator after poking finishes
        if not all_success:
            print("Warning: One or more poke operations failed.")
            sys.exit(1) # Exit with error code if any poke failed
        else:
            sys.exit(0) # Implicit success exit

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
            print(f"\nFound {len(devices)} Apricorn device(s):") # Added count
            for idx, dev in enumerate(devices, start=1):
                print(f"\n=== Apricorn Device #{idx} ===")
                try:
                    # Use vars() for dataclasses, handle dicts as fallback (e.g., if scan partially failed)
                    attributes = vars(dev) if hasattr(dev, '__dataclass_fields__') else dev
                except TypeError:
                    attributes = dev if isinstance(dev, dict) else {} # Fallback

                if attributes and isinstance(attributes, dict):
                    # Determine longest key for alignment (optional, improves readability)
                    max_key_len = 0
                    try:
                        max_key_len = max(len(str(k)) for k in attributes.keys())
                    except ValueError: # Handle empty attributes dict
                        pass

                    for field_name, value in attributes.items():
                        # Simple alignment: Pad field name
                        print(f"  {str(field_name):<{max_key_len}} : {value}")
                elif isinstance(dev, object) and not isinstance(dev, dict):
                     # Fallback for non-dict, non-dataclass objects
                     print(f"  Device Info: {dev}")
                else: # Should not happen if attributes is dict but empty
                     print(f"  Device Info: (Could not display attributes)")
            print() # Add a final newline

# --- Entry Point for direct execution ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130) # Standard exit code for Ctrl+C
    except SystemExit as e:
        # Catch SystemExit to prevent it being caught by the generic Exception handler
        # sys.exit() calls raise SystemExit
        sys.exit(e.code) # Propagate the intended exit code
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1) # Generic error exit code
