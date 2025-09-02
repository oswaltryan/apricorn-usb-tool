# tests/collect_mac_data.py
"""
A utility script to automatically capture mock data for testing mac_usb.py.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(command):
    """Executes a command and returns its stdout."""
    try:
        # For the ioreg pipeline, we need to run it through a shell.
        is_shell_cmd = isinstance(command, str)
        result = subprocess.run(
            command,
            shell=is_shell_cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e.stderr.strip()}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"Error: command not found: {command[0]}", file=sys.stderr)
        return None


def capture_data(scenario_name: str):
    """Main function to capture all necessary data for a given scenario."""
    if not shutil.which("lsusb"):
        print("Error: 'lsusb' command not found.", file=sys.stderr)
        print("Please install it via Homebrew: 'brew install lsusb'", file=sys.stderr)
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / "tests" / "mock_data" / "macos" / scenario_name
    print(f"Creating mock data in: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Capture system_profiler USB data ---
    print("Capturing system_profiler data...")
    profiler_cmd = ["system_profiler", "SPUSBDataType", "-json"]
    profiler_out = run_command(profiler_cmd)
    if profiler_out is not None:
        (output_dir / "system_profiler_usb.json").write_text(
            profiler_out, encoding="utf-8"
        )

    # --- 2. Capture ioreg UAS info ---
    print("Capturing ioreg UAS data...")
    # This command is complex and best run via shell
    ioreg_cmd = r"""
ioreg -p IOUSB -w0 -l | awk '
/"USB Product Name"/ { product=$0 }
/"IOClass"/ {
    if ($3 == "\"IOUSBAttachedSCSI\"") {
        uas=1
    } else {
        uas=0
    }
    if (product && uas >= 0) {
        gsub(/.*= /, "", product)
        gsub(/"/, "", product)
        print product ": " (uas ? "UAS" : "Not UAS")
        product=""
        uas=-1
    }
}' | sort
"""
    ioreg_out = run_command(ioreg_cmd)
    if ioreg_out is not None:
        (output_dir / "ioreg_uas.txt").write_text(ioreg_out, encoding="utf-8")

    # --- 3. Capture lsusb base output ---
    print("Capturing lsusb data...")
    lsusb_out = run_command(["lsusb"])
    if lsusb_out is not None:
        (output_dir / "lsusb.txt").write_text(lsusb_out, encoding="utf-8")

    print("\nmacOS data collection complete.")
    print(f"Please review the files in {output_dir} for accuracy.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture mock data for mac_usb.py tests."
    )
    parser.add_argument(
        "scenario", help="The name for the test scenario (e.g., 'single_device_m1')."
    )
    args = parser.parse_args()
    capture_data(args.scenario)
