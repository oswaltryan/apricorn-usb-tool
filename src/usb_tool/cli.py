# src/usb_tool/cli.py

import argparse
import ctypes
import json
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SYSTEM = platform.system().lower()
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def is_admin_windows() -> bool:
    if not _SYSTEM.startswith("win"):
        return False
    try:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        shell32 = getattr(windll, "shell32", None)
        if shell32 is None:
            return False
        is_user_an_admin = getattr(shell32, "IsUserAnAdmin", None)
        if is_user_an_admin is None:
            return False
        return bool(is_user_an_admin())
    except (AttributeError, Exception):
        return False


def _is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _should_pause_before_exit() -> bool:
    if not _SYSTEM.startswith("win"):
        return False

    force_pause = os.getenv("USB_TOOL_PAUSE_ON_EXIT", "").strip().lower()
    if force_pause in _TRUTHY_VALUES:
        return True

    disable_pause = os.getenv("USB_TOOL_NO_PAUSE", "").strip().lower()
    if disable_pause in _TRUTHY_VALUES:
        return False

    if not _is_frozen_app():
        return False

    # Avoid blocking scripted invocations that pass arguments.
    if len(sys.argv) > 1:
        return False

    # Common case: packaged exe launched directly with no arguments.
    return True


def _pause_before_exit_if_needed() -> None:
    if not _should_pause_before_exit():
        return
    _wait_for_user_acknowledgement()


def _wait_for_user_acknowledgement() -> None:
    if _SYSTEM.startswith("win"):
        try:
            import msvcrt

            print("\nPress any key to close...", end="", flush=True)
            getwch = getattr(msvcrt, "getwch", None)
            if callable(getwch):
                getwch()
            else:
                getch = getattr(msvcrt, "getch", None)
                if callable(getch):
                    getch()
                else:
                    raise RuntimeError("No console key reader available")
            print()
            return
        except Exception:
            pass
    try:
        input("\nPress Enter to close...")
    except Exception:
        pass


def _error_log_path() -> Path:
    override = os.getenv("USB_TOOL_ERROR_LOG", "").strip()
    if override:
        return Path(override)

    for var in ("TEMP", "TMP"):
        value = os.getenv(var, "").strip()
        if value:
            return Path(value) / "usb_tool_error.log"
    return Path.cwd() / "usb_tool_error.log"


def _write_startup_error_log(exc: BaseException) -> str | None:
    path = _error_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"\n[{timestamp}] usb startup error\n")
            fh.write(tb_text)
        return str(path)
    except OSError:
        return None


def _load_print_help():
    try:
        from usb_tool.help_text import print_help as _print_help

        return _print_help
    except Exception:
        from .help_text import print_help as _print_help

        return _print_help


def _load_device_manager_class():
    try:
        from usb_tool.services import DeviceManager as _DeviceManager

        return _DeviceManager
    except Exception:
        from .services import DeviceManager as _DeviceManager

        return _DeviceManager


def _devices_to_json_payload(devices: list[Any]) -> dict[str, list[dict[str, Any]]]:
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


def _handle_list_action(devices: list[Any], json_mode: bool = False) -> None:
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
    poke_input: str, devices: list[Any]
) -> tuple[list[tuple[str, Any]], list[str]]:
    targets: list[tuple[str, Any]] = []
    skipped: list[str] = []
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
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid format") from exc
    return targets, skipped


def main() -> None:
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
        print_help = _load_print_help()
        print_help()
        sys.exit(0)

    if args.json and args.poke:
        parser.error("--json cannot be used together with --poke.")

    DeviceManager = _load_device_manager_class()
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
        if _SYSTEM.startswith("win") and not is_admin_windows():
            parser.error("--poke requires Administrator privileges on Windows.")

        try:
            targets, skipped = _parse_poke_targets(args.poke, devices)
        except ValueError as e:
            parser.error(str(e))

        if not targets and not skipped:
            print("\nNo valid targets specified for poke.\n")
            return

        print()
        for label, identifier in targets:
            if identifier == -1:
                print(f"  Device {label}: SKIPPED (OOB Mode / No drive index)")
                continue

            print(f"Poking device {label}...")
            try:
                if manager.poke(identifier):
                    print(f"  Device {label}: SUCCESS")
                else:
                    print(f"  Device {label}: FAILED")
            except Exception as e:
                print(f"  Device {label}: ERROR ({e})")

        for label in skipped:
            print(f"  Device {label}: SKIPPED")
        print()
    else:
        _handle_list_action(devices, json_mode=args.json)


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        exit_code = 130
    except SystemExit as e:
        if isinstance(e.code, int):
            exit_code = e.code
        else:
            exit_code = 0 if e.code is None else 1
    except Exception as e:
        log_path = _write_startup_error_log(e)
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        if log_path:
            print(f"Full traceback saved to: {log_path}", file=sys.stderr)
        traceback.print_exc()
        exit_code = 1
    finally:
        _pause_before_exit_if_needed()
    sys.exit(exit_code)
