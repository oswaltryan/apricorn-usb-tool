# src/usb_tool/cli.py

import platform
import sys
import argparse
import ctypes
import json
from typing import List, Tuple, Any

from .help_text import print_help
from .services import DeviceManager
from .models import UsbDeviceInfo

_SYSTEM = platform.system().lower()


def is_admin_windows():
    if not _SYSTEM.startswith("win"):
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, Exception):
        return False


def _devices_to_json_payload(
    devices: list[UsbDeviceInfo],
) -> dict[str, list[dict[str, Any]]]:
    devices_mapping = {str(i + 1): dev.to_dict() for i, dev in enumerate(devices)}
    for dev_dict in devices_mapping.values():
        dev_dict.pop("bridgeFW", None)
    return {"devices": [devices_mapping] if devices_mapping else []}


def _json_default(value: Any) -> Any:
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _handle_list_action(devices: list[UsbDeviceInfo], json_mode: bool = False) -> None:
    if json_mode:
        payload = _devices_to_json_payload(devices)
        print(json.dumps(payload, indent=2, default=_json_default))
        return

    if not devices:
        print("\nNo Apricorn devices found.\n")
        return

    print(f"\nFound {len(devices)} Apricorn device(s):")
    for idx, dev in enumerate(devices, start=1):
        print(f"\n=== Apricorn Device #{idx} ===")
        printable = dev.to_dict()
        printable.pop("bridgeFW", None)
        max_key_len = max((len(str(k)) for k in printable.keys()), default=0)
        for field_name, value in printable.items():
            print(f"  {str(field_name):<{max_key_len}} : {value}")
    print()


def _parse_poke_targets(
    poke_input: str, devices: list
) -> Tuple[List[Tuple[str, Any]], List[str]]:
    # Ported logic from legacy cross_usb.py
    targets = []
    skipped: List[str] = []
    if poke_input.lower() == "all":
        for i, d in enumerate(devices):
            targets.append((f"#{i+1}", getattr(d, "physicalDriveNum", -1)))
    else:
        elements = [s.strip() for s in poke_input.split(",") if s.strip()]
        if not elements:
            raise ValueError("No targets")
        for part in elements:
            try:
                idx = int(part)
                if 1 <= idx <= len(devices):
                    targets.append(
                        (f"#{idx}", getattr(devices[idx - 1], "physicalDriveNum", -1))
                    )
                else:
                    raise ValueError("Out of range")
            except (ValueError, TypeError):
                raise ValueError("Invalid format")
    return targets, skipped


def main():
    parser = argparse.ArgumentParser(
        description="USB tool for Apricorn devices.", add_help=False
    )
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("-p", "--poke", type=str, metavar="TARGETS")
    parser.add_argument("--json", action="store_true")
    if _SYSTEM.startswith("win"):
        parser.add_argument("--minimal", action="store_true")

    args = parser.parse_args()

    if args.help:
        print_help()
        sys.exit(0)

    if args.json and args.poke:
        parser.error("--json cannot be used together with --poke.")

    manager = DeviceManager()

    scan_message = "Scanning for Apricorn devices..."
    if args.json:
        print(scan_message, file=sys.stderr)
    else:
        print(scan_message)

    try:
        devices = manager.list_devices(minimal=getattr(args, "minimal", False))
    except Exception as e:
        print(f"Error during device scan: {e}", file=sys.stderr)
        devices = None

    if devices is None:
        print("Device scan failed.", file=sys.stderr)
        sys.exit(1)

    if args.poke:
        # Poke logic implementation (simplified for now to use manager.poke)
        if _SYSTEM.startswith("win") and not is_admin_windows():
            parser.error("--poke requires Administrator privileges on Windows.")

        # Very simplified poke targets parsing for demo/transition
        if args.poke.lower() == "all":
            targets = [
                (f"#{i+1}", getattr(d, "physicalDriveNum", -1))
                for i, d in enumerate(devices)
            ]
        else:
            try:
                idx = int(args.poke)
                if 1 <= idx <= len(devices):
                    targets = [
                        (f"#{idx}", getattr(devices[idx - 1], "physicalDriveNum", -1))
                    ]
                else:
                    targets = []
            except (ValueError, TypeError):
                targets = []

        print()
        for label, identifier in targets:
            if identifier == -1:
                continue
            print(f"Poking device {label}...")
            if manager.poke(identifier):
                pass  # Success message handled by being silent or as needed
            else:
                print(f"  Device {label}: Poke FAILED")
        print()
    else:
        _handle_list_action(devices, json_mode=args.json)


if __name__ == "__main__":
    main()
