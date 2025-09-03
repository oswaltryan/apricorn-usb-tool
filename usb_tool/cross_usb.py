# usb_tool/cross_usb.py

import platform
import sys
import argparse
import ctypes
import os  # For path validation on Linux
from typing import List, Tuple, Optional, Callable, Any, Type

# Optional: device version query (READ BUFFER 0x3C)
query_device_version: Optional[Callable[..., Any]]
try:
    from .device_version import query_device_version as _query_device_version

    query_device_version = _query_device_version
except Exception:
    query_device_version = None

# --- Platform check and conditional import ---
_SYSTEM = platform.system().lower()

POKE_AVAILABLE = False


# On supported platforms, attempt to import the real implementations.
if _SYSTEM.startswith(("win", "linux", "darwin")):
    # Alias type that will point to the real or placeholder ScsiError
    PokeScsiError: Type[Exception]
    try:
        # Use relative import for package structure
        from .poke_device import send_scsi_read10, ScsiError as _ImportedScsiError

        POKE_AVAILABLE = True
        PokeScsiError = _ImportedScsiError
    except Exception as e:
        print(f"Warning: Error importing poke_device: {e}", file=sys.stderr)

        # Fallback placeholders when poke_device is not importable
        class _LocalPokeScsiError(Exception):
            """Placeholder exception to ensure static type compatibility."""

            def __init__(self, message, scsi_status=None, sense_data=None, **kwargs):
                super().__init__(message)
                self.scsi_status = scsi_status
                # The only attribute accessed on the exception is sense_hex.
                self.sense_hex = "N/A"

        def send_scsi_read10(
            device_identifier: Any,
            lba: Any = 0,
            blocks: Any = 1,
            block_size: Any = 512,
            timeout: Any = 5,
        ) -> Any:
            """Placeholder function when poke_device is not available."""
            raise NotImplementedError("poke_device module could not be loaded.")

        PokeScsiError = _LocalPokeScsiError


# --- Helper for Admin Check (Windows Only) ---
def is_admin_windows():
    if not _SYSTEM.startswith("win"):
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        return False
    except Exception:
        return False


# --- Helper Function Definition ---
def print_help():
    help_text = ""
    if _SYSTEM.startswith("win"):
        help_text = r"""
NAME
       usb - Cross-platform USB tool for Apricorn devices
       usb-update - Update the usb-tool installation (if installed from Git)

SYNOPSIS
       usb [-h] [-p TARGETS] [--device-version TARGET]
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

       --device-version TARGET
              Query device PIC/bridge/MCU version via READ BUFFER (6).
              Windows: TARGET is a list index (e.g., 1).
              Linux: TARGET is an sg path (e.g., /dev/sg0).

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
        help_text = r"""
NAME
       usb - Cross-platform USB tool for Apricorn devices
       usb-update - Update the usb-tool installation (if installed from Git)

SYNOPSIS
       usb [-h] [-p TARGETS] [--device-version TARGET]
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

       --device-version TARGET
              Query device PIC/bridge/MCU version via READ BUFFER (6).
              Linux: TARGET is an sg path (e.g., /dev/sg0).
              Windows (if run on WSL/dual-boot): unsupported from Linux.

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
    try:
        # Call the cross-platform function
        send_scsi_read10(device_identifier)
        # If successful, the function returns data, but we just need success status here
        # Mimic Windows output format
        # print(f"  Device {device_identifier}: Poke SUCCEEDED.") # Success message handled by caller loop
        return True
    except PokeScsiError as e:
        # Mimic Windows output format
        print(f"  Device {device_identifier}: Poke FAILED (SCSI Error)")
        status_str = (
            f"0x{int(e.scsi_status):02X}" if isinstance(e.scsi_status, int) else "N/A"
        )
        print(f"    Status: {status_str}, Sense: {getattr(e, 'sense_hex', 'N/A')}")
        return False
    except PermissionError as e:
        # Mimic Windows output format (adjusting message slightly)
        privilege = "Admin (Windows)" if _SYSTEM.startswith("win") else "root (Linux)"
        print(
            f"  Device {device_identifier}: Poke FAILED (PermissionError - Run as {privilege})"
        )
        print(f"    Details: {e}")
        return False
    except FileNotFoundError as e:  # Specific error for Linux/macOS paths
        print(
            f"  Device {device_identifier}: Poke FAILED (FileNotFoundError - Path valid?)"
        )
        print(f"    Details: {e}")
        return False
    except OSError as e:
        # General OS error, could be invalid handle/fd, device not ready, etc.
        # Mimic Windows output format
        err_type = (
            "Drive valid?" if _SYSTEM.startswith("win") else "Device valid/ready?"
        )
        print(f"  Device {device_identifier}: Poke FAILED (OSError - {err_type})")
        print(f"    Details: {e}")
        return False
    except ValueError as e:  # e.g., invalid input to send_scsi_read10
        print(f"  Device {device_identifier}: Poke FAILED (ValueError)")
        print(f"    Details: {e}")
        return False
    except NotImplementedError as e:  # If poke isn't supported on this OS
        print(f"  Device {device_identifier}: Poke FAILED (NotImplementedError)")
        print(f"    Details: {e}")
        return False
    except Exception as e:
        # Catch-all for unexpected issues
        print(f"  Device {device_identifier}: Poke FAILED (Unexpected Error)")
        print(f"    Details: {e}")
        return False


def _handle_list_action(devices: list) -> None:
    """Print the details of all discovered devices."""
    if devices is None:
        print("Device scan failed or yielded no results.", file=sys.stderr)
        sys.exit(1)
    if not devices:
        print("\nNo Apricorn devices found.\n")
        return

    print(f"\nFound {len(devices)} Apricorn device(s):")
    for idx, dev in enumerate(devices, start=1):
        print(f"\n=== Apricorn Device #{idx} ===")
        try:
            attributes = vars(dev) if hasattr(dev, "__dataclass_fields__") else dev
        except TypeError:
            attributes = dev if isinstance(dev, dict) else {}

        if attributes and isinstance(attributes, dict):
            max_key_len = 0
            try:
                max_key_len = max(len(str(k)) for k in attributes.keys())
            except ValueError:
                pass
            for field_name, value in attributes.items():
                print(f"  {str(field_name):<{max_key_len}} : {value}")
        elif isinstance(dev, object) and not isinstance(dev, dict):
            print(f"  Device Info: {dev}")
        else:
            print("  Device Info: (Could not display attributes)")
    print()


def _parse_poke_targets(
    poke_input: str, devices: list
) -> Tuple[List[Tuple[str, object]], List[str]]:
    """Parse the ``--poke`` argument into validated targets.

    Returns a tuple containing the targets to poke and any device identifiers
    skipped because they are in OOB mode.
    """
    num_devices = len(devices)
    targets_to_poke: List[Tuple[str, object]] = []
    skipped_oob: List[str] = []
    invalid_inputs: List[str] = []

    if poke_input.lower() == "all":
        for i, dev in enumerate(devices, start=1):
            user_id = f"#{i}"
            os_identifier: object | None = None
            is_oob = False
            size_attr = getattr(dev, "driveSizeGB", "Unknown")
            if str(size_attr).strip().upper().startswith("N/A"):
                is_oob = True
            if _SYSTEM.startswith("win"):
                p_num = getattr(dev, "physicalDriveNum", -1)
                if isinstance(p_num, int) and p_num >= 0:
                    os_identifier = p_num
            elif _SYSTEM.startswith("linux"):
                b_dev = getattr(dev, "blockDevice", "")
                if isinstance(b_dev, str) and b_dev.startswith("/dev/"):
                    os_identifier = b_dev
            if os_identifier is None:
                invalid_inputs.append(f"Device {user_id} (Missing OS ID)")
                continue
            if is_oob:
                skipped_oob.append(user_id)
            else:
                targets_to_poke.append((user_id, os_identifier))
    else:
        elements = [s.strip() for s in poke_input.split(",") if s.strip()]
        if not elements:
            raise ValueError("No device identifiers provided for --poke argument.")
        unique_targets: set[tuple[str, object]] = set()
        for element in elements:
            try:
                idx = int(element)
                if 1 <= idx <= num_devices:
                    dev = devices[idx - 1]
                    os_id: object | None = None
                    is_oob = False
                    size_attr = getattr(dev, "driveSizeGB", "Unknown")
                    if str(size_attr).strip().upper().startswith("N/A"):
                        is_oob = True
                    if _SYSTEM.startswith("win"):
                        p_num = getattr(dev, "physicalDriveNum", -1)
                        if isinstance(p_num, int) and p_num >= 0:
                            os_id = p_num
                    elif _SYSTEM.startswith("linux"):
                        b_dev = getattr(dev, "blockDevice", "")
                        if isinstance(b_dev, str) and b_dev.startswith("/dev/"):
                            os_id = b_dev
                    if os_id is not None:
                        if is_oob:
                            skipped_oob.append(f"#{idx}")
                        else:
                            unique_targets.add((f"#{idx}", os_id))
                    else:
                        invalid_inputs.append(
                            f"{element} (Index valid, failed to get OS ID)"
                        )
                else:
                    invalid_inputs.append(
                        f"{element} (Index out of range 1-{num_devices})"
                    )
            except ValueError:
                if _SYSTEM.startswith("linux") and element.startswith("/dev/"):
                    found = None
                    for i, dev in enumerate(devices, start=1):
                        if getattr(dev, "blockDevice", "") == element:
                            found = (i, dev)
                            break
                    if found:
                        idx, dev = found
                        size_attr = getattr(dev, "driveSizeGB", "Unknown")
                        if str(size_attr).strip().upper().startswith("N/A"):
                            skipped_oob.append(element)
                        else:
                            unique_targets.add((element, element))
                    else:
                        invalid_inputs.append(
                            f"{element} (Path not found for detected Apricorn device)"
                        )
                else:
                    invalid_inputs.append(
                        f"{element} (Invalid format - expected index"
                        + (" or /dev/ path" if _SYSTEM.startswith("linux") else "")
                        + ")"
                    )
        targets_to_poke = list(unique_targets)

    if invalid_inputs:
        raise ValueError("Invalid value(s) for --poke: " + ", ".join(invalid_inputs))
    if not targets_to_poke:
        raise ValueError(
            "No valid, non-OOB Apricorn devices specified or found to poke."
        )
    return targets_to_poke, skipped_oob


def _handle_poke_action(args: argparse.Namespace, devices: list) -> None:
    """Execute the poke workflow."""
    if not (_SYSTEM.startswith("win") or _SYSTEM.startswith("linux")):
        raise ValueError(
            f"--poke option is only available on Windows and Linux (current: {_SYSTEM})."
        )
    if not POKE_AVAILABLE:
        raise ValueError(
            "Poke functionality could not be loaded (poke_device import failed)."
        )

    if _SYSTEM.startswith("win"):
        if not is_admin_windows():
            raise ValueError("--poke requires Administrator privileges on Windows.")
    elif _SYSTEM.startswith("linux"):
        if sys.platform != "win32":
            try:
                if hasattr(os, "geteuid") and os.geteuid() != 0:
                    print(
                        "\nWarning: --poke on Linux typically requires root privileges (use sudo)."
                    )
            except AttributeError:
                print(
                    "\nWarning: Cannot determine user privileges. --poke on Linux typically requires root."
                )

    if devices is None:
        raise ValueError(
            "Device scan failed or yielded no results; cannot validate poke targets."
        )
    if not devices:
        print("No Apricorn devices found. Nothing to poke.")
        sys.exit(0)

    targets_to_poke, skipped_oob = _parse_poke_targets(args.poke.strip(), devices)

    if skipped_oob:
        print(f"Info: Skipping poke for OOB Mode devices: {sorted(skipped_oob)}")

    print()
    results = []
    all_success = True

    def sort_key(target_tuple):
        user_id = target_tuple[0]
        if isinstance(user_id, str) and user_id.startswith("#"):
            try:
                return (0, int(user_id[1:]))
            except ValueError:
                return (1, user_id)
        return (1, str(user_id))

    for user_id, os_id in sorted(targets_to_poke, key=sort_key):
        print(f"Poking device {user_id}...")
        success = sync_poke_drive(os_id)
        results.append(success)
        if not success:
            all_success = False

    print()
    if not all_success:
        print("Warning: One or more poke operations failed.")
        sys.exit(1)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="USB tool for Apricorn devices.",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="Show detailed help/manpage."
    )
    parser.add_argument(
        "--device-version",
        type=str,
        metavar="TARGET",
        help=(
            "Query device PIC/bridge/MCU version. Windows: index from list. "
            "Linux: sg path (e.g., /dev/sg0)."
        ),
    )
    poke_help = (
        "Windows: Poke by device index number shown in list (e.g., 1) or 'all'. "
        "Linux: Poke by index OR block device path (e.g., 1 or /dev/sda) or 'all'. "
        "Requires Admin/root."
    )
    parser.add_argument("-p", "--poke", type=str, metavar="TARGETS", help=poke_help)
    args = parser.parse_args()

    if args.help:
        print_help()
        sys.exit(0)

    if _SYSTEM.startswith("win"):
        from . import windows_usb as os_usb
    elif _SYSTEM.startswith("darwin"):
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
        devices = None

    if devices is None:
        print("Device scan failed. Exiting.", file=sys.stderr)
        sys.exit(1)

    try:
        devices = os_usb.sort_devices(devices)
    except Exception as e:
        print(f"Warning: Could not sort devices: {e}", file=sys.stderr)

    if args.device_version:
        if query_device_version is None:
            parser.error("Device version query module failed to load.")
        # Determine OS-specific target
        tgt = args.device_version.strip()
        try:
            if _SYSTEM.startswith("win"):
                # Windows: treat as list index -> physicalDriveNum
                try:
                    idx = int(tgt)
                except ValueError:
                    parser.error(
                        "On Windows, --device-version expects a device index (e.g., 1)"
                    )
                if not (1 <= idx <= len(devices)):
                    parser.error(f"Index out of range (1-{len(devices)})")
                dev = devices[idx - 1]
                pdn = getattr(dev, "physicalDriveNum", None)
                if pdn is None:
                    parser.error("Selected device missing physicalDriveNum")
                info = query_device_version(int(pdn))
            elif _SYSTEM.startswith("linux"):
                # Linux: require sg path
                if not (tgt.startswith("/dev/sg")):
                    parser.error(
                        "On Linux, --device-version requires an sg path like /dev/sg0"
                    )
                info = query_device_version(tgt)
            else:
                parser.error(
                    "--device-version currently supported on Windows and Linux"
                )
        except (PermissionError, FileNotFoundError, OSError, ValueError) as e:
            print(f"Error querying device version: {e}", file=sys.stderr)
            sys.exit(1)

        # Pretty-print (combine model IDs and hardware revs)
        print("\nDevice Version Information:")
        print(f"  SCB Part Num : {info.scb_part_number}")
        # Prefer combined fields computed in device_version
        model_id = getattr(info, "model_id", None)
        if not model_id:
            if (
                getattr(info, "model_id1", None) is not None
                and getattr(info, "model_id2", None) is not None
            ):
                model_id = f"{info.model_id1}{info.model_id2}"
            else:
                model_id = "N/A"
        hw_ver = getattr(info, "hardware_version", None)
        if not hw_ver:
            if (
                getattr(info, "hardware_major", None) is not None
                and getattr(info, "hardware_minor", None) is not None
            ):
                hw_ver = f"{info.hardware_minor}{info.hardware_major}"
            else:
                hw_ver = "N/A"
        print(f"  Hardware Ver : {hw_ver}")
        print(f"  Model ID     : {model_id}")
        mj, mn, sub = info.mcu_fw
        print(
            f"  MCU FW       : {mj}.{mn}.{sub}"
            if mj is not None and mn is not None and sub is not None
            else "  MCU FW       : N/A"
        )
        print(f"  Bridge FW    : {info.bridge_fw}")
        sys.exit(0)

    if args.poke:
        try:
            _handle_poke_action(args, devices)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        _handle_list_action(devices)


# --- Entry Point for direct execution ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except SystemExit as e:
        # Catch SystemExit to prevent it being caught by the generic Exception handler
        # sys.exit() calls raise SystemExit
        sys.exit(e.code)  # Propagate the intended exit code
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)  # Generic error exit code
