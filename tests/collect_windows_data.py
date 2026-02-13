# tests/collect_windows_data.py
"""
A utility script to automatically capture mock data for testing windows_usb.py.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from pprint import pformat

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from usb_tool.backend.windows import WindowsBackend
except ImportError as e:
    print(f"Failed to import WindowsBackend. Error: {e}")
    sys.exit(1)


def run_powershell_script(script: str) -> str:
    if not script:
        return ""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error running PowerShell script: {e}")
        return ""


def _extract_ps_from_docstring(func) -> str:
    doc = getattr(func, "__doc__", None) or ""
    match = re.search(r'"""(.*?)"""', doc, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def capture_data(scenario_name: str):
    output_dir = project_root / "tests" / "mock_data" / "windows" / scenario_name
    print(f"Creating mock data in: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    backend = WindowsBackend()

    # --- 1. Capture PowerShell JSON Outputs ---
    print("Capturing controller data...")
    # get_all_usb_controller_names was legacy. New is _get_usb_controllers_wmi but that uses WMI now, not PS?
    # Wait, in legacy windows_usb.py, get_all_usb_controller_names used PowerShell.
    # In new WindowsBackend, _get_usb_controllers_wmi uses WMI via win32com.
    # So there is no PS script to extract anymore for controllers!
    # The tests relying on PS output for controllers might be obsolete or need adjustment.
    # But mock data collection is for legacy tests? No, for new tests too if they mock low level.
    # If the new code doesn't use PS, we don't need PS output mock data for it.
    # We need to capture what the new code uses: WMI objects.

    # We'll skip PS capture for controllers if not available.

    # Check readonly status map. In new backend: _get_usb_readonly_status_map_wmi uses WMI.
    # Legacy used PS.

    # So this script essentially needs to dump the return values of the methods now.

    print("Capturing WMI and libusb data...")
    pnp_entities = backend._get_wmi_usb_devices()
    disk_drives = backend._get_wmi_diskdrives()
    usb_drives = backend._get_wmi_usb_drives(disk_drives)
    libusb_data = backend._get_apricorn_libusb_data()

    (output_dir / "pnp_entities.py").write_text(
        f"MOCK_PNP_ENTITIES = {pformat(pnp_entities)}\n", encoding="utf-8"
    )
    (output_dir / "disk_drives.py").write_text(
        f"MOCK_DISK_DRIVES = {pformat(usb_drives)}\n", encoding="utf-8"
    )
    (output_dir / "libusb_data.py").write_text(
        f"MOCK_LIBUSB_DATA = {pformat(libusb_data)}\n", encoding="utf-8"
    )

    print("\nData collection complete (Simplified for WMI backend).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="The name for the test scenario")
    args = parser.parse_args()
    capture_data(args.scenario)
