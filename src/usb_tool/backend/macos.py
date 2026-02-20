# src/usb_tool/backend/macos.py

import subprocess
import json
from typing import List, Any

from .base import AbstractBackend
from ..models import UsbDeviceInfo
from ..utils import bytes_to_gb, find_closest
from ..device_config import get_size_options, is_supported_vid, is_supported_vid_pid

from ..services import populate_device_version, prune_hidden_version_fields



def _normalize_pid(pid: str) -> str:
    if not isinstance(pid, str):
        return ""
    cleaned = pid.lower().replace("0x", "")
    return cleaned.split("&", 1)[0][:4]


class MacOSBackend(AbstractBackend):
    def scan_devices(self, minimal: bool = False) -> List[UsbDeviceInfo]:
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
            if not is_supported_vid_pid(vid, pid):
                continue

            serial = drive.get("serial_num", "")
            bcd_dev = drive.get("bcd_device", "").replace(".", "")

            size_gb = "0"
            media_type = "Unknown"
            bsd_name = ""

            if "Media" in drive and drive["Media"]:
                m = drive["Media"][0]
                size_raw = bytes_to_gb(m.get("size_in_bytes", 0))
                opts = get_size_options(vid, pid, bcd_dev)
                closest = find_closest(size_raw, opts) if opts else None
                size_gb = str(closest) if closest is not None else str(round(size_raw))
                media_type = (
                    "Removable Media"
                    if m.get("removable_media") == "yes"
                    else "Basic Disk"
                )
                bsd_name = m.get("bsd_name", "")
            else:
                size_gb = "N/A (OOB Mode)"

            version_info = populate_device_version(
                int(vid, 16), int(pid, 16), serial, bsd_name=bsd_name
            )

            dev_info = UsbDeviceInfo(
                bcdUSB=(3.0 if int(drive.get("bus_power", "0")) > 500 else 2.0),
                idVendor=vid,
                idProduct=pid,
                bcdDevice=f"0{bcd_dev}" if bcd_dev else "N/A",
                iManufacturer=drive.get("manufacturer", "Apricorn"),
                iProduct=name,
                iSerial=serial,
                SCSIDevice=uas_status.get(name, False),
                driveSizeGB=str(size_gb),
                mediaType=media_type,
                **version_info,
            )
            if bsd_name:
                setattr(dev_info, "blockDevice", bsd_name)

            prune_hidden_version_fields(dev_info)
            devices.append(dev_info)

        return devices

    def poke_device(self, device_identifier: Any) -> bool:
        return False  # Disabled

    def sort_devices(self, devices: List[UsbDeviceInfo]) -> List[UsbDeviceInfo]:
        return sorted(devices, key=lambda d: getattr(d, "iSerial", "") or "~~~~~")

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
                    vendor_id = obj.get("vendor_id", "")
                    vendor = vendor_id.replace("0x", "").lower()[:4]
                    if is_supported_vid(vendor) or "Apricorn" in obj.get(
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
