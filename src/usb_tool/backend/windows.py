# src/usb_tool/backend/windows.py

import ctypes as ct
import re
import subprocess
import sys
import time
from collections import defaultdict
from types import SimpleNamespace
from typing import List, Any, Tuple

try:
    import libusb as usb
except Exception:  # pragma: no cover - exercised on non-Windows CI
    usb = None

try:
    import win32com.client as _win32com_client
except Exception:  # pragma: no cover - exercised on non-Windows CI

    class _MissingWin32ComClient:
        def Dispatch(self, *_args: Any, **_kwargs: Any) -> Any:  # noqa: N802
            raise ImportError("pywin32 is required for Windows backend")

    win32com = SimpleNamespace(client=_MissingWin32ComClient())
else:
    win32com = SimpleNamespace(client=_win32com_client)

from .base import AbstractBackend
from ..models import UsbDeviceInfo
from ..utils import bytes_to_gb, find_closest, parse_usb_version
from ..constants import EXCLUDED_PIDS
from ..device_config import closest_values
from ..services import (
    populate_device_version,
    prune_hidden_version_fields,
)  # We'll need to move this later or import from legacy for now

# For Phase 3, we still import from legacy for cross-module dependencies not yet moved


def _extract_vid_pid(device_id: str) -> Tuple[str, str]:
    if not isinstance(device_id, str):
        return "", ""
    vid_match = re.search(r"VID_([0-9A-Fa-f]{4})", device_id)
    pid_match = re.search(r"PID_([0-9A-Fa-f]{4})", device_id)
    vid = vid_match.group(1).lower() if vid_match else ""
    pid = pid_match.group(1).lower() if pid_match else ""
    return vid, pid


def _is_excluded_pid(pid: str) -> bool:
    if not pid:
        return False
    normalized = pid.lower().split("&", 1)[0].replace("0x", "")
    return normalized in EXCLUDED_PIDS


def _normalize_driver_value(value: Any, default: str = "N/A") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _escape_wmi_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class _StageTimer:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.start = time.perf_counter() if enabled else 0.0
        self.last = self.start
        self.measurements: list[tuple[str, float]] = []

    def mark(self, label: str) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        self.measurements.append((label, (now - self.last) * 1000.0))
        self.last = now

    def emit(self, suffix: str = "") -> None:
        if not self.enabled:
            return
        total_ms = (time.perf_counter() - self.start) * 1000.0
        parts = [
            f"{label}={duration_ms:.2f}ms" for label, duration_ms in self.measurements
        ]
        parts.append(f"total={total_ms:.2f}ms")
        line = "windows-scan-profile"
        if suffix:
            line = f"{line} {suffix}"
        print(f"{line}: {', '.join(parts)}", file=sys.stderr)


class WindowsBackend(AbstractBackend):
    def __init__(self):
        self.locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        self.service = self.locator.ConnectServer(".", "root\\cimv2")
        self._profile_scan_enabled = False
        self._scan_pass_index = 1
        if usb is not None:
            usb.config(LIBUSB=None)

    @property
    def service(self):
        return self._service

    @service.setter
    def service(self, value):
        self._service = value

    def scan_devices(
        self,
        minimal: bool = False,
        expanded: bool = False,
        profile_scan: bool = False,
    ) -> List[UsbDeviceInfo]:
        self._profile_scan_enabled = profile_scan
        self._scan_pass_index = 1
        devices, lengths = self._perform_scan_pass(minimal=minimal, expanded=expanded)
        if not devices and len(set(lengths)) != 1 and any(lengths):
            time.sleep(1.0)
            self._scan_pass_index = 2
            devices, _ = self._perform_scan_pass(minimal=minimal, expanded=expanded)
        return devices or []

    def _perform_scan_pass(self, minimal: bool = False, expanded: bool = False):
        timer = _StageTimer(self._profile_scan_enabled)
        wmi_usb_devices = self._get_wmi_usb_devices()
        timer.mark("wmi_usb_devices")
        wmi_diskdrives = self._get_wmi_diskdrives()
        timer.mark("wmi_diskdrives")
        wmi_usb_drives = self._get_wmi_usb_drives(wmi_diskdrives)
        timer.mark("wmi_usb_drives")
        libusb_data = self._get_apricorn_libusb_data()
        timer.mark("libusb_data")
        physical_drives = self._get_physical_drive_number(wmi_diskdrives)
        timer.mark("physical_drive_map")

        device_ids = {
            device.get("device_id", "")
            for device in wmi_usb_devices
            if device.get("device_id", "")
        }
        if expanded:
            device_ids.update(
                drive.get("pnpdeviceid", "")
                for drive in wmi_usb_drives
                if drive.get("pnpdeviceid", "")
            )
        signed_driver_map: dict[str, dict[str, str]] = {}
        if expanded:
            signed_driver_map = self._get_signed_driver_info_map(device_ids)
        timer.mark("signed_driver_query")
        if expanded:
            self._apply_usb_driver_info(wmi_usb_devices, signed_driver_map)
        timer.mark("apply_usb_driver_info")
        if expanded:
            self._apply_disk_driver_info(wmi_usb_drives, signed_driver_map)
        timer.mark("apply_disk_driver_info")

        wmi_usb_drives = self._sort_wmi_drives(wmi_usb_devices, wmi_usb_drives)
        timer.mark("sort_wmi_drives")

        include_controller = not minimal
        if include_controller:
            usb_controllers = self._get_usb_controllers_wmi()
            usb_controllers = self._sort_usb_controllers(
                wmi_usb_devices, usb_controllers
            )
        else:
            usb_controllers = [{"ControllerName": "N/A"}] * len(wmi_usb_devices)
        timer.mark("usb_controllers")

        libusb_data = self._sort_libusb_data(wmi_usb_devices, libusb_data)
        timer.mark("sort_libusb_data")

        drive_indices = set()
        if not minimal and physical_drives:
            for device, drive in zip(wmi_usb_devices, wmi_usb_drives):
                if drive.get("size_gb", 0.0) > 0:
                    serial = device.get("serial", "")
                    idx = physical_drives.get(serial, -1)
                    if idx >= 0:
                        drive_indices.add(idx)

        readonly_map = self._get_usb_readonly_status_map_wmi()
        timer.mark("readonly_map")
        drive_letters_map = {}
        if not minimal:
            drive_letters_map = self._get_drive_letters_map_wmi(
                wmi_diskdrives, drive_indices
            )
        timer.mark("drive_letters_map")

        devices = self._instantiate_devices(
            wmi_usb_devices,
            wmi_usb_drives,
            usb_controllers,
            libusb_data,
            physical_drives,
            readonly_map,
            drive_letters_map,
            include_controller=include_controller,
            include_drive_letter=not minimal,
        )
        timer.mark("instantiate_devices")
        timer.emit(
            suffix=(
                f"pass={self._scan_pass_index} "
                f"minimal={str(minimal).lower()} expanded={str(expanded).lower()} "
                f"usb={len(wmi_usb_devices)} disks={len(wmi_usb_drives)} "
                f"libusb={len(libusb_data)}"
            )
        )

        return devices, [len(wmi_usb_devices), len(wmi_usb_drives), len(libusb_data)]

    def poke_device(self, device_identifier: Any) -> bool:
        # Simplified version of _windows_read10 from poke_device.py
        import ctypes.wintypes as wintypes

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x1
        FILE_SHARE_WRITE = 0x2
        OPEN_EXISTING = 0x3
        INVALID_HANDLE_VALUE = -1
        IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
        SCSI_IOCTL_DATA_IN = 1

        class SCSI_PASS_THROUGH_DIRECT(ct.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("ScsiStatus", ct.c_byte),
                ("PathId", ct.c_byte),
                ("TargetId", ct.c_byte),
                ("Lun", ct.c_byte),
                ("CdbLength", ct.c_byte),
                ("SenseInfoLength", ct.c_byte),
                ("DataIn", ct.c_byte),
                ("DataTransferLength", wintypes.ULONG),
                ("TimeOutValue", wintypes.ULONG),
                ("DataBuffer", ct.c_void_p),
                ("SenseInfoOffset", wintypes.ULONG),
                ("Cdb", ct.c_byte * 16),
            ]

        class SPTD_WITH_SENSE(ct.Structure):
            _pack_ = 1
            _fields_ = [
                ("sptd", SCSI_PASS_THROUGH_DIRECT),
                ("ucSenseBuf", ct.c_ubyte * 32),
            ]

        windll = getattr(ct, "windll", None)
        if windll is None:
            return False
        kernel32 = getattr(windll, "kernel32", None)
        if kernel32 is None:
            return False

        drive_path = rf"\\.\PhysicalDrive{device_identifier}"
        h_drive = kernel32.CreateFileW(
            drive_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_drive == INVALID_HANDLE_VALUE:
            return False

        try:
            sptd_sense = SPTD_WITH_SENSE()
            ct.memset(ct.byref(sptd_sense), 0, ct.sizeof(sptd_sense))
            sptd = sptd_sense.sptd

            cdb = [0] * 10
            cdb[0] = 0x28  # READ(10)
            cdb[8] = 1  # Transfer 1 block

            data_buffer = ct.create_string_buffer(512)
            sptd.Length = ct.sizeof(SCSI_PASS_THROUGH_DIRECT)
            sptd.CdbLength = 10
            sptd.SenseInfoLength = 32
            sptd.DataIn = SCSI_IOCTL_DATA_IN
            sptd.DataTransferLength = 512
            sptd.TimeOutValue = 5
            sptd.DataBuffer = ct.addressof(data_buffer)
            sptd.SenseInfoOffset = sptd.Length
            ct.memmove(sptd.Cdb, (ct.c_ubyte * 10)(*cdb), 10)

            returned = wintypes.DWORD(0)
            ok = kernel32.DeviceIoControl(
                h_drive,
                IOCTL_SCSI_PASS_THROUGH_DIRECT,
                ct.byref(sptd_sense),
                ct.sizeof(sptd_sense),
                ct.byref(sptd_sense),
                ct.sizeof(sptd_sense),
                ct.byref(returned),
                None,
            )
            return bool(ok and sptd.ScsiStatus == 0)
        finally:
            kernel32.CloseHandle(h_drive)

    def sort_devices(self, devices: List[UsbDeviceInfo]) -> List[UsbDeviceInfo]:
        def _key(dev):
            p_num = getattr(dev, "physicalDriveNum", -1)
            return p_num if isinstance(p_num, int) and p_num >= 0 else float("inf")

        return sorted(devices, key=_key)

    # --- Internal Helpers adapted from legacy windows_usb.py ---

    def get_drive_letter_via_ps(self, drive_index: int) -> str:
        if drive_index < 0:
            return "Not Formatted"
        try:
            cmd = f"(Get-Partition -DiskNumber {drive_index} | Get-Volume).DriveLetter"
            result = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True,
                text=True,
                check=False,
            )
            letter = result.stdout.strip()
            if not letter:
                return "Not Formatted"
            return f"{letter}:" if ":" not in letter else letter
        except Exception:
            return "Not Formatted"

    def _should_retry_scan(self, lengths: list[int]) -> bool:
        if not lengths:
            return False
        if not any(lengths):
            return False
        return len(set(lengths)) != 1

    def _get_wmi_usb_devices(self):
        query = "SELECT * FROM Win32_PnPEntity WHERE DeviceID LIKE 'USB%'"
        devices = self.service.ExecQuery(query)
        info = []
        for d in devices:
            vid, pid = _extract_vid_pid(d.DeviceID)
            if vid == "0984" and not _is_excluded_pid(pid):
                info.append(
                    {
                        "vid": vid,
                        "pid": pid,
                        "manufacturer": "Apricorn",
                        "description": d.Description or "",
                        "device_id": d.DeviceID,
                        "serial": (
                            d.DeviceID.split("\\")[-1] if "\\" in d.DeviceID else ""
                        ),
                        "usbDriverProvider": "N/A",
                        "usbDriverVersion": "N/A",
                        "usbDriverInf": "N/A",
                    }
                )
        return info

    def _get_signed_driver_info_map(
        self, device_ids: set[str]
    ) -> dict[str, dict[str, str]]:
        cleaned_ids = sorted({device_id for device_id in device_ids if device_id})
        if not cleaned_ids:
            return {}

        where_clause = " OR ".join(
            f"DeviceID='{_escape_wmi_string(device_id)}'" for device_id in cleaned_ids
        )
        query = (
            "SELECT DeviceID, DriverProviderName, DriverVersion, InfName "
            f"FROM Win32_PnPSignedDriver WHERE {where_clause}"
        )
        try:
            records = list(self.service.ExecQuery(query))
        except Exception:
            return {}

        info_map = {}
        for record in records:
            device_id = _normalize_driver_value(getattr(record, "DeviceID", None), "")
            if not device_id:
                continue
            info_map[device_id] = {
                "provider": _normalize_driver_value(
                    getattr(record, "DriverProviderName", None)
                ),
                "version": _normalize_driver_value(
                    getattr(record, "DriverVersion", None)
                ),
                "inf": _normalize_driver_value(getattr(record, "InfName", None)),
            }
        return info_map

    def _get_signed_driver_info(self, device_id: str) -> dict[str, str]:
        return self._get_signed_driver_info_map({device_id}).get(
            device_id, {"provider": "N/A", "version": "N/A", "inf": "N/A"}
        )

    def _apply_usb_driver_info(
        self,
        wmi_usb_devices: list[dict[str, Any]],
        driver_info_map: dict[str, dict[str, str]],
    ) -> None:
        for device in wmi_usb_devices:
            info = driver_info_map.get(device.get("device_id", ""), {})
            device["usbDriverProvider"] = info.get("provider", "N/A")
            device["usbDriverVersion"] = info.get("version", "N/A")
            device["usbDriverInf"] = info.get("inf", "N/A")

    def _apply_disk_driver_info(
        self,
        wmi_usb_drives: list[dict[str, Any]],
        driver_info_map: dict[str, dict[str, str]],
    ) -> None:
        for drive in wmi_usb_drives:
            drive["diskDriverInfo"] = driver_info_map.get(
                drive.get("pnpdeviceid", ""),
                {"provider": "N/A", "version": "N/A", "inf": "N/A"},
            )

    def _classify_driver_transport(
        self, usb_device: dict[str, Any], usb_drive: dict[str, Any], scsi_device: bool
    ) -> str:
        pnp_id = str(usb_drive.get("pnpdeviceid", "")).upper()
        if pnp_id.startswith("SCSI\\"):
            return "UAS"
        if pnp_id.startswith("USBSTOR\\"):
            return "BOT"

        provider = str(usb_device.get("usbDriverProvider", "")).strip().lower()
        if provider.startswith("apricorn"):
            return "Vendor"
        if scsi_device:
            return "UAS"
        return "Unknown"

    def _get_wmi_diskdrives(self):
        try:
            return list(
                self.service.ExecQuery(
                    "SELECT DeviceID, PNPDeviceID, Caption, Size, MediaType, InterfaceType, Index FROM Win32_DiskDrive"
                )
            )
        except Exception:
            return []

    def _get_wmi_usb_drives(self, wmi_diskdrives):
        drives = [d for d in wmi_diskdrives if getattr(d, "InterfaceType", "") == "USB"]
        info = []
        for d in drives:
            if (
                "Apricorn" in getattr(d, "Caption", "")
                and getattr(d, "Size", None) is not None
            ):
                pnp = d.PNPDeviceID
                if not pnp:
                    continue
                i_product = ""
                try:
                    if "USBSTOR" in pnp:
                        i_product = (
                            pnp[pnp.index("PROD_") + 5 : pnp.index("&REV")]
                            .replace("_", " ")
                            .title()
                        )
                    elif "SCSI" in pnp:
                        i_product = (
                            pnp.split("PROD_", 1)[1].split("\\", 1)[0].replace("_", " ")
                        )
                        if "NVX" in i_product:
                            i_product = (
                                "Padlock NVX" if i_product == "PADLOCK NVX" else ""
                            )
                        elif "PORTABLE" in i_product:
                            i_product = (
                                "Aegis Portable"
                                if i_product == " AEGIS PORTABLE"
                                else ""
                            )
                except Exception:
                    pass
                info.append(
                    {
                        "caption": d.Caption,
                        "size_gb": bytes_to_gb(int(d.Size)),
                        "iProduct": i_product,
                        "pnpdeviceid": pnp,
                        "mediaType": (
                            "Basic Disk"
                            if "External hard disk" in d.MediaType
                            else "Removable Media"
                        ),
                        "diskDriverInfo": {
                            "provider": "N/A",
                            "version": "N/A",
                            "inf": "N/A",
                        },
                    }
                )
        return info

    def _get_apricorn_libusb_data(self):
        if usb is None:
            return []
        devices = []
        ctx = ct.POINTER(usb.context)()
        if usb.init(ct.byref(ctx)) != 0:
            return []
        try:
            dev_list = ct.POINTER(ct.POINTER(usb.device))()
            cnt = usb.get_device_list(ctx, ct.byref(dev_list))
            for i in range(cnt):
                dev = dev_list[i]
                desc = usb.device_descriptor()
                if usb.get_device_descriptor(dev, ct.byref(desc)) == 0:
                    vid = f"{desc.idVendor:04x}"
                    pid = f"{desc.idProduct:04x}"
                    if vid == "0984" and not _is_excluded_pid(pid):
                        devices.append(
                            {
                                "iProduct": pid,
                                "bcdDevice": f"{desc.bcdDevice:04x}",
                                "bcdUSB": float(parse_usb_version(desc.bcdUSB)),
                                "bus_number": usb.get_bus_number(dev),
                                "dev_address": usb.get_device_address(dev),
                            }
                        )
            usb.free_device_list(dev_list, 1)
        finally:
            usb.exit(ctx)
        return devices

    def _get_physical_drive_number(self, wmi_diskdrives):
        drives = {}
        for r in wmi_diskdrives or []:
            if "SATAWIRE" in r.PNPDeviceID or "FLASH_DISK" in r.PNPDeviceID:
                continue
            if "APRI" in r.PNPDeviceID:
                try:
                    # Index is the physical drive number (e.g., 0 for \\.\PhysicalDrive0)
                    drive_num = int(r.Index)
                    # Extract serial from PNPDeviceID (last part before suffix)
                    # Example: USBSTOR\DISK&VEN_APRICORN&PROD_AEGIS_PADLOCK\0123456789ABCDEF&0
                    serial_part = r.PNPDeviceID.rsplit("\\", 1)[1]
                    serial = serial_part.split("&")[0]
                    drives[serial] = drive_num
                except (ValueError, TypeError, IndexError):
                    continue
        return drives

    def _get_usb_controllers_wmi(self):
        controllers = []
        try:
            records = self.service.ExecQuery("SELECT * FROM Win32_USBControllerDevice")
            for r in records:
                try:
                    ctrl = self.service.Get(r.Antecedent)
                    dev = self.service.Get(r.Dependent)
                    vid, pid = _extract_vid_pid(dev.DeviceID)
                    if vid == "0984" and not _is_excluded_pid(pid):
                        controllers.append(
                            {
                                "DeviceID": str(dev.DeviceID).upper(),
                                "ControllerName": (
                                    ctrl.Name[:5]
                                    if ctrl.Name.startswith("Intel")
                                    else "ASMedia"
                                ),
                            }
                        )
                except Exception:
                    continue
        except Exception:
            pass
        return controllers

    def _get_usb_readonly_status_map_wmi(self):
        try:
            storage = self.locator.ConnectServer(
                ".", "root\\Microsoft\\Windows\\Storage"
            )
            disks = storage.ExecQuery(
                "SELECT Number, IsReadOnly, BusType FROM MSFT_Disk"
            )
            return {
                int(d.Number): bool(d.IsReadOnly) for d in disks if int(d.BusType) == 7
            }
        except Exception:
            return {}

    def _get_drive_letters_map_wmi(self, wmi_diskdrives, drive_indices):
        mapping = {}
        if not drive_indices:
            if self._profile_scan_enabled:
                print(
                    "windows-drive-letter-profile: "
                    f"pass={self._scan_pass_index} skipped=no_candidate_drive_indices",
                    file=sys.stderr,
                )
            return mapping

        try:
            partition_links = list(
                self.service.ExecQuery(
                    "SELECT Antecedent, Dependent FROM Win32_DiskDriveToDiskPartition"
                )
            )
            logical_links = list(
                self.service.ExecQuery(
                    "SELECT Antecedent, Dependent FROM Win32_LogicalDiskToPartition"
                )
            )
        except Exception:
            if self._profile_scan_enabled:
                print(
                    "windows-drive-letter-profile: "
                    f"pass={self._scan_pass_index} stage=bulk_query_exception "
                    f"error={sys.exc_info()[1]}",
                    file=sys.stderr,
                )
            return mapping

        partition_to_letters: dict[str, list[str]] = {}
        for link in logical_links:
            antecedent = str(getattr(link, "Antecedent", "") or "")
            dependent = str(getattr(link, "Dependent", "") or "")
            partition_to_letters.setdefault(antecedent, []).append(dependent)

        for d in wmi_diskdrives or []:
            try:
                idx = int(d.Index)
            except (TypeError, ValueError):
                continue

            if drive_indices and idx not in drive_indices:
                continue

            escaped_device_id = _escape_wmi_string(
                str(getattr(d, "DeviceID", "") or "")
            )
            disk_token = f'DeviceID="{escaped_device_id}"'
            index_token = f"Index={idx}"
            matching_partitions: list[str] = []
            for link in partition_links:
                antecedent = str(getattr(link, "Antecedent", "") or "")
                dependent = str(getattr(link, "Dependent", "") or "")
                if disk_token in antecedent or index_token in antecedent:
                    matching_partitions.append(dependent)

            if self._profile_scan_enabled:
                print(
                    "windows-drive-letter-profile: "
                    f"pass={self._scan_pass_index} disk_index={idx} "
                    f"stage=bulk_partitions count={len(matching_partitions)} "
                    f"device_id={getattr(d, 'DeviceID', '')}",
                    file=sys.stderr,
                )

            letters: list[str] = []
            for partition in matching_partitions:
                partition_letters = partition_to_letters.get(partition, [])
                letters.extend(partition_letters)
                if self._profile_scan_enabled:
                    print(
                        "windows-drive-letter-profile: "
                        f"pass={self._scan_pass_index} disk_index={idx} "
                        f"stage=bulk_partition_result "
                        f"partition={partition} letters={', '.join(partition_letters) or 'none'}",
                        file=sys.stderr,
                    )

            mapping[idx] = ", ".join(letters) if letters else "Not Formatted"
        return mapping

    def _sort_wmi_drives(self, wmi_usb_devices, wmi_usb_drives):
        drives_to_process = list(wmi_usb_drives)
        sorted_drives = []
        for device in wmi_usb_devices:
            serial = device.get("serial", "")
            found_idx = -1
            best_score = -1
            for i, drive in enumerate(drives_to_process):
                pnp_id = drive["pnpdeviceid"]
                instance_id = pnp_id.rsplit("\\", 1)[-1]
                pnp_serial = instance_id.split("&")[0]
                score = -1
                if serial and serial == pnp_serial:
                    score = 3
                elif serial and (pnp_serial in serial or serial in pnp_serial):
                    score = 2
                elif (
                    "SCSI" in device.get("description", "")
                    and "SCSI" in pnp_id
                    and "PADLOCK_NVX" in pnp_id
                ):
                    score = 1
                if score > best_score:
                    best_score = score
                    found_idx = i
            if found_idx != -1 and best_score > 0:
                sorted_drives.append(drives_to_process.pop(found_idx))
        return sorted_drives + drives_to_process

    def _sort_usb_controllers(self, wmi_usb_devices, usb_controllers):
        to_process = list(usb_controllers)
        sorted_ctrls = []
        for device in wmi_usb_devices:
            serial = device["serial"]
            for i, ctrl in enumerate(to_process):
                if ctrl["DeviceID"].rsplit("\\", 1)[-1] == serial:
                    sorted_ctrls.append(to_process.pop(i))
                    break
        return sorted_ctrls + to_process

    def _sort_libusb_data(self, wmi_usb_devices, libusb_data):
        if not libusb_data:
            return []
        pid_map = defaultdict(list)
        for entry in libusb_data:
            pid_map[entry.get("iProduct")].append(entry)

        sorted_data = []
        used = set()
        for device in wmi_usb_devices:
            pid = device.get("pid")
            candidates = pid_map.get(pid, [])
            candidates.sort(key=lambda x: x.get("bcdUSB", 0.0), reverse=True)
            best = None
            for c in candidates:
                key = (c.get("iProduct"), c.get("bcdDevice"))
                if key not in used:
                    best = c
                    used.add(key)
                    break
            if not best and candidates:
                best = candidates[0]
            sorted_data.append(
                best
                or {
                    "iProduct": pid,
                    "bcdDevice": "0000",
                    "bcdUSB": 0.0,
                    "bus_number": -1,
                    "dev_address": -1,
                }
            )
        return sorted_data

    def _instantiate_devices(
        self,
        wmi_usb_devices,
        wmi_usb_drives,
        usb_controllers,
        libusb_data,
        physical_drives,
        readonly_map,
        drive_letters_map,
        include_controller,
        include_drive_letter,
    ):
        devices = []
        version_query_ms = 0.0
        drive_letter_fallback_ms = 0.0
        count = min(
            len(wmi_usb_devices),
            len(wmi_usb_drives),
            len(usb_controllers),
            len(libusb_data),
        )
        for i in range(count):
            pid = wmi_usb_devices[i]["pid"]
            vid = wmi_usb_devices[i]["vid"]
            serial = wmi_usb_devices[i]["serial"]
            if serial.startswith("MSFT30"):
                scsi, serial = True, serial[6:]
            else:
                scsi = False
            driver_transport = self._classify_driver_transport(
                wmi_usb_devices[i], wmi_usb_drives[i], scsi
            )

            drive_num = -1
            if physical_drives:
                for k, v in physical_drives.items():
                    if k == serial:
                        drive_num = v
                        break

            size_raw = wmi_usb_drives[i]["size_gb"]
            size_gb = (
                "N/A (OOB Mode)"
                if size_raw == 0.0
                else find_closest(size_raw, closest_values[pid][1])
            )

            version_info = (
                {}
                if not serial
                else self._timed_populate_device_version(
                    vid,
                    pid,
                    serial,
                    drive_num,
                )
            )
            version_query_ms += version_info.pop("_profile_ms", 0.0)

            dev_info = UsbDeviceInfo(
                bcdUSB=libusb_data[i]["bcdUSB"],
                idVendor=vid,
                idProduct=pid,
                bcdDevice=libusb_data[i]["bcdDevice"],
                iManufacturer="Apricorn",
                iProduct=wmi_usb_drives[i]["iProduct"],
                iSerial=serial,
                SCSIDevice=scsi,
                driverTransport=driver_transport,
                driveSizeGB=size_gb,
                mediaType=wmi_usb_drives[i].get("mediaType", "Unknown"),
                usbDriverProvider=wmi_usb_devices[i].get("usbDriverProvider", "N/A"),
                usbDriverVersion=wmi_usb_devices[i].get("usbDriverVersion", "N/A"),
                usbDriverInf=wmi_usb_devices[i].get("usbDriverInf", "N/A"),
                diskDriverProvider=wmi_usb_drives[i]
                .get("diskDriverInfo", {})
                .get("provider", "N/A"),
                diskDriverVersion=wmi_usb_drives[i]
                .get("diskDriverInfo", {})
                .get("version", "N/A"),
                diskDriverInf=wmi_usb_drives[i]
                .get("diskDriverInfo", {})
                .get("inf", "N/A"),
                **version_info,
            )
            if include_controller:
                setattr(dev_info, "usbController", usb_controllers[i]["ControllerName"])
            else:
                try:
                    delattr(dev_info, "usbController")
                except AttributeError:
                    pass
            setattr(dev_info, "busNumber", libusb_data[i]["bus_number"])
            setattr(dev_info, "deviceAddress", libusb_data[i]["dev_address"])
            setattr(dev_info, "physicalDriveNum", drive_num)
            if include_drive_letter:
                drive_letter = drive_letters_map.get(drive_num, "Not Formatted")
                if (
                    size_raw != 0.0
                    and isinstance(drive_num, int)
                    and drive_num >= 0
                    and drive_letter == "Not Formatted"
                ):
                    if self._profile_scan_enabled:
                        print(
                            "windows-drive-letter-profile: "
                            f"pass={self._scan_pass_index} disk_index={drive_num} "
                            f"stage=fallback_triggered "
                            f"serial={serial} size_raw={size_raw}",
                            file=sys.stderr,
                        )
                    drive_letter_start = time.perf_counter()
                    drive_letter = self.get_drive_letter_via_ps(drive_num)
                    drive_letter_fallback_ms += (
                        time.perf_counter() - drive_letter_start
                    ) * 1000.0
                    if self._profile_scan_enabled:
                        print(
                            "windows-drive-letter-profile: "
                            f"pass={self._scan_pass_index} disk_index={drive_num} "
                            f"stage=fallback_result "
                            f"letter={drive_letter or 'Not Formatted'}",
                            file=sys.stderr,
                        )
                setattr(dev_info, "driveLetter", drive_letter or "Not Formatted")
            else:
                try:
                    delattr(dev_info, "driveLetter")
                except AttributeError:
                    pass
            setattr(dev_info, "readOnly", readonly_map.get(drive_num, False))

            prune_hidden_version_fields(dev_info)
            devices.append(dev_info)
        if self._profile_scan_enabled:
            print(
                "windows-scan-profile details: "
                f"pass={self._scan_pass_index} "
                f"populate_device_version_total={version_query_ms:.2f}ms, "
                f"drive_letter_fallback_total={drive_letter_fallback_ms:.2f}ms, "
                f"device_count={count}",
                file=sys.stderr,
            )
        return devices

    def _timed_populate_device_version(
        self, vid: str, pid: str, serial: str, drive_num: int
    ) -> dict[str, Any]:
        start = time.perf_counter()
        version_info = populate_device_version(
            int(vid, 16),
            int(pid, 16),
            serial,
            physical_drive_num=drive_num if drive_num != -1 else None,
        )
        version_info["_profile_ms"] = (time.perf_counter() - start) * 1000.0
        return version_info
