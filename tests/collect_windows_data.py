# tests/collect_windows_data.py
"""
A utility script to automatically capture mock data for testing windows_usb.py.

This script should be run on a Windows machine with the target Apricorn
hardware connected. It will generate a full set of mock data files for a
given test scenario.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from pprint import pformat

# Add the project root to the Python path to allow importing usb_tool
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    # We import the actual functions to get access to their PowerShell scripts
    # and to run the real WMI/libusb queries.
    from usb_tool import windows_usb
except ImportError as e:
    print("Failed to import usb_tool. Ensure you have run 'pip install .'")
    print(f"Error: {e}")
    sys.exit(1)


def run_powershell_script(script: str) -> str:
    """Executes a PowerShell script and returns its stdout."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running PowerShell script: {e.stderr}")
        return ""
    except FileNotFoundError:
        print("Error: powershell.exe not found in PATH.")
        return ""


def _extract_ps_from_docstring(func) -> str:
    """Extract a PowerShell script embedded in a function docstring.

    Returns an empty string if no triple-quoted content is found or the
    docstring is absent. This avoids Optional access errors under type checkers.
    """
    doc = getattr(func, "__doc__", None) or ""
    match = re.search(r'"""(.*?)"""', doc, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def capture_data(scenario_name: str):
    """
    Main function to capture all necessary data for a given scenario.
    """
    output_dir = project_root / "tests" / "mock_data" / "windows" / scenario_name
    print(f"Creating mock data in: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Capture PowerShell JSON Outputs ---
    print("Capturing controller data...")
    controllers_script = _extract_ps_from_docstring(
        windows_usb.get_all_usb_controller_names
    )
    controllers_json = run_powershell_script(controllers_script)
    (output_dir / "controllers.json").write_text(controllers_json, encoding="utf-8")

    print("Capturing read-only status...")
    readonly_script = _extract_ps_from_docstring(
        windows_usb.get_usb_readonly_status_map
    )
    readonly_json = run_powershell_script(readonly_script)
    (output_dir / "readonly_status.json").write_text(readonly_json, encoding="utf-8")

    # --- 2. Capture WMI and libusb Python Object Data ---
    print("Capturing WMI and libusb data...")
    # These functions return Python objects. We'll format them and write to .py files.
    pnp_entities = windows_usb.get_wmi_usb_devices()
    disk_drives = windows_usb.get_wmi_usb_drives()
    libusb_data = windows_usb.get_apricorn_libusb_data()

    (output_dir / "pnp_entities.py").write_text(
        f"# Mock data for get_wmi_usb_devices()\nMOCK_PNP_ENTITIES = {pformat(pnp_entities)}\n",
        encoding="utf-8",
    )
    (output_dir / "disk_drives.py").write_text(
        f"# Mock data for get_wmi_usb_drives()\nMOCK_DISK_DRIVES = {pformat(disk_drives)}\n",
        encoding="utf-8",
    )
    (output_dir / "libusb_data.py").write_text(
        f"# Mock data for get_apricorn_libusb_data()\nMOCK_LIBUSB_DATA = {pformat(libusb_data)}\n",
        encoding="utf-8",
    )

    # --- 3. Capture Drive Letter Outputs ---
    print("Capturing drive letters...")
    if disk_drives:
        # We need to find the physical drive index from the captured disk_drives data
        for drive in disk_drives:
            if not isinstance(drive, dict):
                continue
            pnp_id = str(drive.get("pnpdeviceid", ""))
            if "APRI" in pnp_id:  # Heuristic to find the right drive
                # A more robust method might be needed if multiple drives are present
                physical_drives_raw = windows_usb.get_physical_drive_number()
                physical_drives: dict[str, int] = (
                    physical_drives_raw if isinstance(physical_drives_raw, dict) else {}
                )
                serial = pnp_id.rsplit("\\", 1)[-1].split("&")[0]
                drive_index = physical_drives.get(serial)

                if drive_index is not None:
                    print(
                        f"Found drive index {drive_index} for serial {serial}. Capturing its drive letter."
                    )
                    letter_script = _extract_ps_from_docstring(
                        windows_usb.get_drive_letter_via_ps
                    )
                    letter_script = (
                        letter_script.format(drive_index=drive_index)
                        if letter_script
                        else ""
                    )
                    drive_letter = (
                        run_powershell_script(letter_script) if letter_script else ""
                    )
                    (output_dir / f"drive_letter_pd{drive_index}.txt").write_text(
                        drive_letter, encoding="utf-8"
                    )

    print("\nData collection complete.")
    print(
        f"Please review the files in {output_dir} for accuracy and to ensure no sensitive information is present."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture mock data for windows_usb.py tests."
    )
    parser.add_argument(
        "scenario", help="The name for the test scenario (e.g., 'single_device_l3')."
    )
    args = parser.parse_args()
    capture_data(args.scenario)
