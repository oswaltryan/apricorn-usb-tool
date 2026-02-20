# src/usb_tool/help_text.py

import platform
from ._version import get_version as get_local_version

_SYSTEM = platform.system().lower()


def print_help():
    """
    Prints platform-specific help text (Man page style) with dynamic versioning.
    Includes a standard Unix-style header and footer.
    """
    # 1. Resolve Version safely
    tool_ver = get_local_version()

    # 2. Define Header and Footer
    # Header: COMMAND(Section) | Title | Source/Version
    header = "USB(1)                              User Commands                              USB(1)"

    # Footer: Standard man pages often repeat the name/version at the bottom
    footer = f"\nVERSION\n       v{tool_ver}"

    help_text = ""

    if _SYSTEM.startswith("win"):
        help_text = rf"""{header}

NAME
       usb - Cross-platform USB tool for supported devices (Windows)

SYNOPSIS
       usb [-h] [-p TARGETS]

DESCRIPTION
       The usb-tool utility scans the system for connected supported USB devices
       (Vendor ID 0984) using WMI and displays detailed information. It can
       also send a basic SCSI READ(10) command (poke) to specified devices.

       The poke operation requires Administrator privileges.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected
              drives. TARGETS should be a comma-separated list of physical
              drive numbers (e.g., '1', '0,2' - corresponding to \\.\PhysicalDriveX)
              or the keyword 'all' to target all detected, non-OOB drives.
              This operation requires Administrator privileges.

              Devices detected in Out-Of-Box (OOB) mode (reporting size as N/A)
              will be skipped.

       --json
              Emit JSON as {{"devices":[{{"<index>":{{...}}}}]}} for automation.
              Each object key matches the numbered list output. Mutually
              exclusive with --poke.

       --minimal
              Faster scan that omits controller name and drive letter fields.
              Output remains otherwise unchanged.

EXAMPLES
       usb
              List all detected supported devices.

       usb -p 1
              (Run as Admin) Send a SCSI READ(10) command to PhysicalDrive1.

       usb -p all
              (Run as Admin) Poke all valid devices.
"""
    elif _SYSTEM.startswith("linux"):
        help_text = rf"""{header}

NAME
       usb - Cross-platform USB tool for supported devices (Linux)

SYNOPSIS
       usb [-h] [-p TARGETS]

DESCRIPTION
       The usb-tool utility scans the system for connected supported USB devices.

       On Linux, full scanning details (lshw, fdisk) often require root or
       specific sudoers configuration. The poke operation strictly requires
       root privileges to access block devices.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected
              drives. TARGETS should be a comma-separated list of block device
              paths (e.g., '/dev/sda', '/dev/sda,/dev/sdb') or the keyword
              'all'.

              This operation requires root privileges (e.g., sudo).

       --json
              Emit JSON as {{"devices":[{{"<index>":{{...}}}}]}} for automation.
              Each object key matches the numbered list output. Mutually
              exclusive with --poke.

EXAMPLES
       usb
              List devices (details may be limited without root).

       sudo usb -p /dev/sdb
              Send a SCSI READ(10) command to the device at /dev/sdb.
"""
    elif _SYSTEM.startswith("darwin"):
        help_text = rf"""{header}

NAME
       usb - Cross-platform USB tool for supported devices (macOS)

SYNOPSIS
       usb [-h] [-p TARGETS]

DESCRIPTION
       The usb-tool utility scans the system for connected supported USB devices
       using IOKit/system_profiler. It can also send a basic SCSI READ(10)
       command (poke) to specified devices.

       On macOS, scanning is generally allowed as a standard user, but sending
       SCSI commands (poking) requires root privileges (sudo) to access the
       raw disk devices.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected
              drives. TARGETS should be a comma-separated list of disk paths
              (e.g., '/dev/disk2', '/dev/disk2,/dev/disk3') or the keyword
              'all'.

              This operation requires root privileges.

       --json
              Emit JSON as {{"devices":[{{"<index>":{{...}}}}]}} for automation.
              Each object key matches the numbered list output. Mutually
              exclusive with --poke.

EXAMPLES
       usb
              List all detected supported devices.

       sudo usb -p /dev/disk2
              (Run with sudo) Send a SCSI READ(10) command to the
              device identified as /dev/disk2.

       sudo usb -p all
              (Run with sudo) Poke all valid devices.
"""
    else:
        # Fallback for unknown operating systems
        help_text = (
            f"usb-tool {tool_ver}: Platform {_SYSTEM} not supported for help text.\n"
            "Please refer to the README or run with valid arguments."
        )

    # Print the body followed by the footer
    print(help_text + footer)
