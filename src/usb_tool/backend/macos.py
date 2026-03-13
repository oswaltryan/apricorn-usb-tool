# src/usb_tool/backend/macos.py

import json
import os
import plistlib
import re
import subprocess
from typing import List, Any

from .base import AbstractBackend
from ..models import UsbDeviceInfo
from ..utils import bytes_to_gb, find_closest
from ..device_config import closest_values

from ..services import populate_device_version, prune_hidden_version_fields

from ..constants import EXCLUDED_PIDS


def _normalize_pid(pid: str) -> str:
    if not isinstance(pid, str):
        return ""
    cleaned = pid.lower().replace("0x", "")
    return cleaned.split("&", 1)[0][:4]


def _is_excluded_pid(pid: str) -> bool:
    return _normalize_pid(pid) in EXCLUDED_PIDS


def _normalize_whole_disk_path(bsd_name: str) -> str:
    if not isinstance(bsd_name, str):
        return ""

    disk_name = bsd_name.strip()
    if disk_name.startswith("/dev/"):
        disk_name = disk_name.removeprefix("/dev/")

    if not disk_name.startswith("disk"):
        return ""

    disk_name = re.sub(r"s\d+$", "", disk_name)
    return f"/dev/{disk_name}"


def _normalize_raw_disk_path(device_path: str) -> str:
    if not isinstance(device_path, str):
        return ""

    normalized = device_path.strip()
    if normalized.startswith("/dev/rdisk"):
        return normalized
    if normalized.startswith("/dev/disk"):
        return normalized.replace("/dev/disk", "/dev/rdisk", 1)
    return ""


def _classify_media_type(removable_value: Any) -> str:
    if isinstance(removable_value, bool):
        return "Removable Media" if removable_value else "Basic Disk"

    text = str(removable_value).strip().lower()
    if text in {"yes", "true", "1"}:
        return "Removable Media"
    if text in {"no", "false", "0"}:
        return "Basic Disk"
    return "Unknown"


def _fallback_media_type(pid: str, product_name: str) -> str:
    product_hint = closest_values.get(pid, ("", []))[0]
    normalized = " ".join(part for part in (product_name, product_hint) if part).lower()
    if any(
        token in normalized for token in ("secure key", "fortress", "padlock", "aegis")
    ):
        return "Basic Disk"
    return "Unknown"


class MacOSBackend(AbstractBackend):
    def scan_devices(
        self,
        expanded: bool = False,
        profile_scan: bool = False,
    ) -> List[UsbDeviceInfo]:
        all_drives = self._list_usb_drives()
        uas_status = self._parse_uasp_info(all_drives)

        devices = []
        for drive in all_drives:
            name = drive.get("_name")
            if not name:
                continue

            vid = drive.get("vendor_id", "").replace("0x", "")[:4].lower()
            pid_raw = drive.get("product_id", "").replace("0x", "").lower()
            pid = _normalize_pid(pid_raw)
            if vid != "0984" or _is_excluded_pid(pid):
                continue

            serial = drive.get("serial_num", "")
            bcd_dev = drive.get("bcd_device", "").replace(".", "")

            size_gb = "0"
            media_type = "Unknown"
            bsd_name = ""
            block_device = ""

            if "Media" in drive and drive["Media"]:
                m = drive["Media"][0]
                size_raw = bytes_to_gb(m.get("size_in_bytes", 0))
                closest = find_closest(size_raw, closest_values.get(pid, (0, []))[1])
                size_gb = str(closest) if closest is not None else "0"
                media_type = _classify_media_type(m.get("removable_media"))
                bsd_name = m.get("bsd_name", "")
                block_device = _normalize_whole_disk_path(bsd_name)
            else:
                size_gb = "N/A (OOB Mode)"

            if media_type == "Unknown" and block_device:
                media_type = self._get_media_type_from_diskutil(block_device)

            if media_type == "Unknown":
                media_type = _fallback_media_type(pid, name)

            version_info = populate_device_version(
                int(vid, 16), int(pid, 16), serial, bsd_name=block_device or bsd_name
            )

            dev_info = UsbDeviceInfo(
                bcdUSB=(3.0 if int(drive.get("bus_power", "0")) > 500 else 2.0),
                idVendor=vid,
                idProduct=pid,
                bcdDevice=f"0{bcd_dev}" if bcd_dev else "N/A",
                iManufacturer=drive.get("manufacturer", "Apricorn"),
                iProduct=name,
                iSerial=serial,
                driverTransport=("UAS" if uas_status.get(name, False) else "Unknown"),
                driveSizeGB=str(size_gb),
                mediaType=media_type,
                **version_info,
            )
            if block_device:
                setattr(dev_info, "blockDevice", block_device)

            prune_hidden_version_fields(dev_info)
            devices.append(dev_info)

        return devices

    def poke_device(self, device_identifier: Any) -> bool:
        raw_disk_path = _normalize_raw_disk_path(str(device_identifier))
        if not raw_disk_path:
            return False

        fd = -1
        try:
            # A single-sector read is the macOS equivalent of a safe diagnostic poke.
            fd = os.open(raw_disk_path, os.O_RDONLY)
            os.lseek(fd, 0, os.SEEK_SET)
            return len(os.read(fd, 512)) > 0
        except OSError:
            return False
        finally:
            if fd >= 0:
                os.close(fd)

    def sort_devices(self, devices: List[UsbDeviceInfo]) -> List[UsbDeviceInfo]:
        def _key(device: UsbDeviceInfo) -> str:
            block_device = getattr(device, "blockDevice", "")
            if isinstance(block_device, str) and block_device.startswith("/dev/disk"):
                return block_device
            return getattr(device, "iSerial", "") or "~~~~~"

        return sorted(devices, key=_key)

    def list_usb_drives(self):
        return self._list_usb_drives()

    def parse_uasp_info(self, drives=None):
        return self._parse_uasp_info(drives or [])

    def find_apricorn_device(self):
        return self.scan_devices()

    def _list_usb_drives(self):
        try:
            res = subprocess.run(
                ["system_profiler", "SPUSBDataType", "-json"],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                return []
            data = json.loads(res.stdout)
            matches = []

            def recurse(obj):
                if isinstance(obj, dict):
                    if "0984" in obj.get("vendor_id", "") or "Apricorn" in obj.get(
                        "manufacturer", ""
                    ):
                        matches.append(obj)
                    for v in obj.values():
                        recurse(v)
                elif isinstance(obj, list):
                    for i in obj:
                        recurse(i)

            recurse(data.get("SPUSBDataType", []))
            return matches
        except Exception:
            return []

    def _parse_uasp_info(self, drives):
        uas = {}
        for d in drives:
            name = d.get("_name")
            if "Media" in d and d["Media"]:
                bsd = d["Media"][0].get("bsd_name")
                if name and bsd:
                    try:
                        res = subprocess.run(
                            ["diskutil", "info", bsd], capture_output=True, text=True
                        )
                        if (
                            res.returncode == 0
                            and "Protocol: USB" in res.stdout
                            and "Transport: UAS" in res.stdout
                        ):
                            uas[name] = True
                    except Exception:
                        pass
        return uas

    def _get_media_type_from_diskutil(self, block_device: str) -> str:
        try:
            res = subprocess.run(
                ["diskutil", "info", "-plist", block_device],
                capture_output=True,
                check=False,
            )
        except Exception:
            return "Unknown"

        if res.returncode != 0 or not res.stdout:
            return "Unknown"

        try:
            info = plistlib.loads(res.stdout)
        except Exception:
            return "Unknown"

        for key in ("RemovableMedia", "Removable", "EjectableOnly"):
            media_type = _classify_media_type(info.get(key))
            if media_type != "Unknown":
                return media_type

        return "Unknown"
