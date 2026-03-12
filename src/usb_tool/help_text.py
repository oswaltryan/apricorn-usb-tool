"""Man-page-style help output for the usb CLI."""

from __future__ import annotations

import platform

from ._version import get_version as get_local_version

_SYSTEM = platform.system().lower()
_HEADER = "USB(1)                              User Commands                              USB(1)"


def _footer(version: str) -> str:
    return f"\nVERSION\n       v{version}"


def _windows_help() -> str:
    return rf"""{_HEADER}

NAME
       usb - Cross-platform USB tool for Apricorn devices (Windows)

SYNOPSIS
       usb [-h] [-p TARGETS] [--json]

DESCRIPTION
       The usb-tool utility scans the system for connected Apricorn USB devices
       (Vendor ID 0984) using WMI and displays detailed information. It can
       also send a basic SCSI READ(10) command (poke) to specified devices.

       The poke operation requires Administrator privileges.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected Apricorn
              drives. TARGETS should be a comma-separated list of physical
              drive numbers (for example '1' or '1,3', matching the numbered
              device list) or the keyword 'all' to target all detected,
              non-OOB Apricorn drives.

              Devices detected in Out-Of-Box (OOB) mode (reporting size as N/A)
              are skipped automatically.

       --json
              Emit JSON as {{"devices":[{{"<index>":{{...}}}}]}} for automation.
              Each object key matches the numbered list output. Mutually
              exclusive with --poke.

EXAMPLES
       usb
              List all detected Apricorn devices.

       usb -p 1
              (Run as Administrator) Send a SCSI READ(10) command to the
              device shown as Apricorn Device #1.

       usb -p all
              (Run as Administrator) Poke all valid Apricorn devices.
"""


def _linux_help() -> str:
    return rf"""{_HEADER}

NAME
       usb - Cross-platform USB tool for Apricorn devices (Linux)

SYNOPSIS
       usb [-h] [-p TARGETS] [--json]

DESCRIPTION
       The usb-tool utility scans the system for connected Apricorn USB devices
       (Vendor ID 0984) and prints normalized USB, storage, and transport
       details.

       Linux enumeration can run as a standard user, but full detail often
       depends on tools such as lsusb, lsblk, and lshw. The poke operation
       requires root privileges because it opens the underlying block device.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected Apricorn
              drives. TARGETS should be a comma-separated list of numbered
              device entries (for example '1' or '1,3'), block device paths
              (for example '/dev/sdb' or '/dev/sdb,/dev/sdc'), or the keyword
              'all'.

              Devices detected in Out-Of-Box (OOB) mode (reporting size as N/A)
              are skipped automatically.

              This operation requires root privileges (for example sudo).

       --json
              Emit JSON as {{"devices":[{{"<index>":{{...}}}}]}} for automation.
              Each object key matches the numbered list output. Mutually
              exclusive with --poke.

EXAMPLES
       usb
              List detected Apricorn devices. Some detail may be unavailable
              without root or optional helper tools.

       sudo usb -p 1
              Send a SCSI READ(10) command to the device shown as Apricorn
              Device #1.

       sudo usb -p /dev/sdb
              Send a SCSI READ(10) command to the Apricorn device at /dev/sdb.

       sudo usb -p all
              Poke all valid Apricorn devices.
"""


def _macos_help() -> str:
    return rf"""{_HEADER}

NAME
       usb - Cross-platform USB tool for Apricorn devices (macOS)

SYNOPSIS
       usb [-h] [-p TARGETS] [--json]

DESCRIPTION
       The usb-tool utility scans the system for connected Apricorn USB devices
       using IOKit/system_profiler. It can also send a basic SCSI READ(10)
       command (poke) to specified devices.

       On macOS, scanning is generally allowed as a standard user, but sending
       SCSI commands (poking) requires root privileges to access raw disk
       devices. End-to-end CLI poke remains disabled for now.

OPTIONS
       -h, --help
              Show this help message and exit.

       -p TARGETS, --poke TARGETS
              Send a SCSI READ(10) command to specified detected Apricorn
              drives. TARGETS should be a comma-separated list of disk paths
              (for example '/dev/disk2' or '/dev/disk2,/dev/disk3') or the
              keyword 'all'.

              This operation requires root privileges.

       --json
              Emit JSON as {{"devices":[{{"<index>":{{...}}}}]}} for automation.
              Each object key matches the numbered list output. Mutually
              exclusive with --poke.

EXAMPLES
       usb
              List all detected Apricorn devices.

       sudo usb -p /dev/disk2
              Attempt to poke the Apricorn device identified as /dev/disk2.

       sudo usb -p all
              Attempt to poke all valid Apricorn devices.
"""


def print_help() -> None:
    """Print platform-specific help text with runtime version information."""
    tool_ver = get_local_version()
    version_banner = f"usb-tool {tool_ver}\n"

    if _SYSTEM.startswith("win"):
        help_text = _windows_help()
    elif _SYSTEM.startswith("linux"):
        help_text = _linux_help()
    elif _SYSTEM.startswith("darwin"):
        help_text = _macos_help()
    else:
        help_text = (
            f"usb-tool {tool_ver}: Platform {_SYSTEM} not supported for help text.\n"
            "Please refer to the README or run with valid arguments.\n"
        )
        print(help_text)
        return

    print(version_banner + help_text + _footer(tool_ver))
