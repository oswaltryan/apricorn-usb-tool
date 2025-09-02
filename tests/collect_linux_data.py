# tests/collect_linux_data.py
"""
A utility script to automatically capture mock data for testing linux_usb.py.

This script MUST be run as root (using sudo) to get complete output from
lshw and lsusb -v.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable


def _geteuid() -> int:
    """Return effective UID if available; default to 0 on non-POSIX.

    This keeps type checkers happy on Windows, where os.geteuid is absent,
    while preserving correct behavior on Linux at runtime.
    """
    get_euid: Callable[[], int] | None = getattr(os, "geteuid", None)  # type: ignore[attr-defined]
    if callable(get_euid):
        try:
            return int(get_euid())
        except Exception:
            return 0
    return 0


def run_command(command, as_root: bool = False):
    """Executes a command and returns its stdout."""
    if as_root and _geteuid() != 0:
        command.insert(0, "sudo")

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, encoding="utf-8"
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(
            f"Error running command '{' '.join(command)}': {e.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    except FileNotFoundError:
        print(f"Error: command not found: {command[0]}", file=sys.stderr)
        return None


def capture_data(scenario_name: str):
    """Main function to capture all necessary data for a given scenario."""
    if _geteuid() != 0:
        print(
            "Error: This script must be run as root (use 'sudo python ...').",
            file=sys.stderr,
        )
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / "tests" / "mock_data" / "linux" / scenario_name
    print(f"Creating mock data in: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Capture lsblk, lshw, and lsusb base output ---
    print("Capturing lsblk data...")
    lsblk_cmd = [
        "lsblk",
        "-p",
        "-o",
        "NAME,SERIAL,SIZE,RM",
        "-d",
        "-n",
        "-l",
        "-e",
        "7",
    ]
    lsblk_out = run_command(lsblk_cmd)
    if lsblk_out is not None:
        (output_dir / "lsblk.txt").write_text(lsblk_out, encoding="utf-8")

    print("Capturing lshw data...")
    lshw_cmd = ["lshw", "-class", "disk", "-class", "storage", "-json"]
    lshw_out = run_command(lshw_cmd)  # sudo is implied by root check
    if lshw_out is not None:
        (output_dir / "lshw.json").write_text(lshw_out, encoding="utf-8")

    print("Capturing lsusb data...")
    lsusb_out = run_command(["lsusb"])
    if lsusb_out is not None:
        (output_dir / "lsusb.txt").write_text(lsusb_out, encoding="utf-8")

        # --- 2. Capture detailed lsusb -v for each Apricorn device found ---
        print("Parsing lsusb output to find Apricorn devices for detailed scan...")
        apricorn_pids = set()
        for line in lsusb_out.split("\n"):
            if "0984:" in line:
                match = re.search(r"ID\s+0984:([0-9a-fA-F]{4})", line)
                if match:
                    apricorn_pids.add(match.group(1).lower())

        if not apricorn_pids:
            print("Warning: No Apricorn devices found in lsusb scan.")
        else:
            for pid in apricorn_pids:
                print(f"Capturing detailed info for device 0984:{pid}...")
                vid_pid = f"0984:{pid}"
                lsusb_v_cmd = ["lsusb", "-v", "-d", vid_pid]
                lsusb_v_out = run_command(lsusb_v_cmd)  # sudo is implied
                if lsusb_v_out is not None:
                    (output_dir / f"lsusb_v_{vid_pid}.txt").write_text(
                        lsusb_v_out, encoding="utf-8"
                    )

    print("\nLinux data collection complete.")
    print(f"Please review the files in {output_dir} for accuracy.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture mock data for linux_usb.py tests."
    )
    parser.add_argument(
        "scenario", help="The name for the test scenario (e.g., 'single_device_uas')."
    )
    args = parser.parse_args()
    capture_data(args.scenario)
