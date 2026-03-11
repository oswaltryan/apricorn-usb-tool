# src/usb_tool/backend/linux.py

import subprocess
import re
import os
import json
from typing import List, Any

from .base import AbstractBackend
from ..models import UsbDeviceInfo
from ..utils import bytes_to_gb, find_closest
from ..constants import EXCLUDED_PIDS
from ..device_config import closest_values

# For Phase 3/4, still import from legacy if not moved
from ..services import populate_device_version, prune_hidden_version_fields


def _normalize_pid(pid: str) -> str:
    if not isinstance(pid, str):
        return ""
    cleaned = pid.lower().replace("0x", "")
    return cleaned.split("&", 1)[0][:4]


def _is_excluded_pid(pid: str) -> bool:
    return _normalize_pid(pid) in EXCLUDED_PIDS


class LinuxBackend(AbstractBackend):
    def scan_devices(
        self,
        minimal: bool = False,
        expanded: bool = False,
        profile_scan: bool = False,
    ) -> List[UsbDeviceInfo]:
        lshw_data = self._parse_uasp_info()
        lsblk_drives = self._list_usb_drives()
        lsblk_map = {info["name"]: info for info in lsblk_drives if info.get("name")}

        lsusb_details = self._get_lsusb_details()

        devices = []
        for block_path, lsblk_info in lsblk_map.items():
            serial = lsblk_info.get("serial")
            lshw_entry = lshw_data.get(block_path) or {}
            if lshw_entry and lshw_entry.get("serial"):
                serial = lshw_entry["serial"]

            if not serial:
                continue

            lsusb_info = lsusb_details.get(serial)
            if not lsusb_info:
                continue

            vid = lsusb_info.get("idVendor", "").lower()
            pid = _normalize_pid(lsusb_info.get("idProduct", ""))
            if vid != "0984" or pid in EXCLUDED_PIDS:
                continue

            bcd_usb = 0.0
            try:
                bcd_usb = float(lsusb_info.get("bcdUSB", "0"))
            except (ValueError, TypeError):
                pass

            bcd_dev = (
                lsusb_info.get("bcdDevice", "0000")
                .lower()
                .replace("0x", "")
                .replace(".", "")
                .zfill(4)
            )

            size_raw = lsblk_info.get("size_gb", 0.0)
            size_gb = "N/A (OOB Mode)"
            if size_raw > 0:
                opts = (
                    closest_values.get(pid, (None, []))[1]
                    or closest_values.get(bcd_dev, (None, []))[1]
                )
                if opts:
                    closest = find_closest(size_raw, opts)
                    size_gb = str(closest) if closest else str(round(size_raw))
                else:
                    size_gb = str(round(size_raw))

            version_info = populate_device_version(int(vid, 16), int(pid, 16), serial)

            dev_info = UsbDeviceInfo(
                bcdUSB=bcd_usb,
                idVendor=vid,
                idProduct=pid,
                bcdDevice=bcd_dev,
                iManufacturer=lsusb_info.get("iManufacturer", "Apricorn"),
                iProduct=lsusb_info.get("iProduct", "Unknown"),
                iSerial=serial,
                SCSIDevice=(lshw_entry.get("driver") == "uas"),
                driverTransport=self._classify_driver_transport(lshw_entry),
                driveSizeGB=size_gb,
                mediaType=lsblk_info.get("mediaType", "Unknown"),
                **version_info,
            )
            setattr(dev_info, "blockDevice", block_path)

            prune_hidden_version_fields(dev_info)
            devices.append(dev_info)

        return devices

    def poke_device(self, device_identifier: Any) -> bool:
        # Ported logic from poke_device.py

        try:
            fd = os.open(device_identifier, os.O_RDWR)
            # This is a stub for the complex IOCTL logic
            os.close(fd)
            return True  # Assume success for now if we can open it
        except OSError:
            return False

    def sort_devices(self, devices: List[UsbDeviceInfo]) -> List[UsbDeviceInfo]:
        def _key(dev):
            path = getattr(dev, "blockDevice", "")
            return path if path.startswith("/dev/") else "~~~~~"

        return sorted(devices, key=_key)

    # --- Internal Helpers ---
    def list_usb_drives(self):
        return self._list_usb_drives()

    def _list_usb_drives(self):
        cmd = ["lsblk", "-p", "-o", "NAME,SERIAL,SIZE,RM", "-d", "-n", "-l", "-e", "7"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                return []
            drives = []
            for line in res.stdout.splitlines():
                parts = line.split(None, 3)
                if len(parts) < 4 or not parts[1] or parts[1] == "-":
                    continue
                drives.append(
                    {
                        "name": parts[0],
                        "serial": parts[1],
                        "size_gb": self.parse_lsblk_size(parts[2]),
                        "mediaType": (
                            "Removable Media" if parts[3] == "1" else "Basic Disk"
                        ),
                    }
                )
            return drives
        except Exception:
            return []

    def parse_lsblk_size(self, size_str: str) -> float:
        if not size_str:
            return 0.0
        m = re.match(r"([\d\.,]+)\s*([GMTEK])?", size_str.upper())
        if not m:
            return 0.0
        val = float(m.group(1).replace(",", ""))
        unit = m.group(2)
        if unit == "G":
            return val
        if unit == "M":
            return val / 1024
        if unit == "T":
            return val * 1024
        if unit == "K":
            return val / (1024**2)
        if unit == "E":
            return val * (1024**2)
        return bytes_to_gb(val)

    def _parse_uasp_info(self):
        try:
            res = subprocess.run(
                ["lshw", "-class", "disk", "-class", "storage", "-json"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return {}

        if res.returncode != 0 or not res.stdout.strip():
            return {}

        try:
            raw_data = json.loads(res.stdout)
        except json.JSONDecodeError:
            return {}

        entries = raw_data if isinstance(raw_data, list) else [raw_data]
        by_block_device: dict[str, dict[str, str]] = {}

        def _walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk(item)
                return

            if not isinstance(node, dict):
                return

            logical_name = node.get("logicalname")
            if isinstance(logical_name, str) and logical_name.startswith("/dev/"):
                by_block_device[logical_name] = {
                    "driver": str(node.get("driver", "")).strip().lower(),
                    "serial": str(node.get("serial", "")).strip(),
                }

            for child in node.get("children", []) or []:
                _walk(child)

        _walk(entries)
        return by_block_device

    def _classify_driver_transport(self, lshw_entry: dict[str, Any] | None) -> str:
        driver_name = str((lshw_entry or {}).get("driver", "")).strip().lower()
        if driver_name == "uas":
            return "UAS"
        if driver_name == "usb-storage":
            return "BOT"
        if driver_name:
            return "Vendor"
        return "Unknown"

    def _get_lsusb_details(self):
        try:
            res = subprocess.run(["lsusb"], capture_output=True, text=True, check=False)
        except Exception:
            return {}

        if res.returncode != 0:
            return {}

        apricorn_pairs = {
            match.group(1).lower()
            for match in re.finditer(r"ID\s+0984:([0-9a-fA-F]{4})", res.stdout)
        }
        details: dict[str, dict[str, str]] = {}

        for pid in apricorn_pairs:
            try:
                verbose = subprocess.run(
                    ["lsusb", "-v", "-d", f"0984:{pid}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                continue

            if verbose.returncode != 0:
                continue

            current: dict[str, str] = {}
            for line in verbose.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith("idVendor"):
                    current["idVendor"] = "0984"
                elif stripped.startswith("idProduct"):
                    match = re.search(r"idProduct\s+0x([0-9a-fA-F]{4})", stripped)
                    if match:
                        current["idProduct"] = match.group(1).lower()
                elif stripped.startswith("bcdUSB"):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        current["bcdUSB"] = parts[1]
                elif stripped.startswith("bcdDevice"):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        current["bcdDevice"] = parts[1]
                elif stripped.startswith("iManufacturer"):
                    current["iManufacturer"] = stripped.split(None, 2)[-1]
                elif stripped.startswith("iProduct"):
                    current["iProduct"] = stripped.split(None, 2)[-1]
                elif stripped.startswith("iSerial"):
                    serial = stripped.split(None, 2)[-1]
                    if serial and serial != "0":
                        current["iSerial"] = serial
                        details[serial] = current.copy()
                        current = {}

        return details
