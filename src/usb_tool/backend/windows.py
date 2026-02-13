# src/usb_tool/backend/windows.py

import ctypes as ct
import re
import subprocess
import time
from collections import defaultdict
from typing import List, Any, Tuple

import libusb as usb
import win32com.client

from .base import AbstractBackend
from ..models import UsbDeviceInfo
from ..utils import bytes_to_gb, find_closest, parse_usb_version
from ..constants import EXCLUDED_PIDS
from ..device_config import closest_values
from ..services import (
    populate_device_version,
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


class WindowsBackend(AbstractBackend):
    def __init__(self):
        self.locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        self.service = self.locator.ConnectServer(".", "root\\cimv2")
        usb.config(LIBUSB=None)

    @property
    def service(self):
        return self._service

    @service.setter
    def service(self, value):
        self._service = value

    def scan_devices(self, minimal: bool = False) -> List[UsbDeviceInfo]:
        devices, lengths = self._perform_scan_pass(minimal=minimal)
        if not devices and len(set(lengths)) != 1 and any(lengths):
            time.sleep(1.0)
            devices, _ = self._perform_scan_pass(minimal=minimal)
        return devices or []

    def _perform_scan_pass(self, minimal: bool = False):
        wmi_usb_devices = self._get_wmi_usb_devices()
        wmi_diskdrives = self._get_wmi_diskdrives()
        wmi_usb_drives = self._get_wmi_usb_drives(wmi_diskdrives)
        libusb_data = self._get_apricorn_libusb_data()
        physical_drives = self._get_physical_drive_number(wmi_diskdrives)

        wmi_usb_drives = self._sort_wmi_drives(wmi_usb_devices, wmi_usb_drives)

        include_controller = not minimal
        if include_controller:
            usb_controllers = self._get_usb_controllers_wmi()
            usb_controllers = self._sort_usb_controllers(
                wmi_usb_devices, usb_controllers
            )
        else:
            usb_controllers = [{"ControllerName": "N/A"}] * len(wmi_usb_devices)

        libusb_data = self._sort_libusb_data(wmi_usb_devices, libusb_data)

        drive_indices = set()
        if not minimal and physical_drives:
            for device, drive in zip(wmi_usb_devices, wmi_usb_drives):
                if drive.get("size_gb", 0.0) > 0:
                    serial = device.get("serial", "")
                    idx = physical_drives.get(serial, -1)
                    if idx >= 0:
                        drive_indices.add(idx)

        readonly_map = self._get_usb_readonly_status_map_wmi()
        drive_letters_map = {}
        if not minimal:
            drive_letters_map = self._get_drive_letters_map_wmi(
                wmi_diskdrives, drive_indices if drive_indices else None
            )

        return self._instantiate_devices(
            wmi_usb_devices,
            wmi_usb_drives,
            usb_controllers,
            libusb_data,
            physical_drives,
            readonly_map,
            drive_letters_map,
            include_controller=include_controller,
            include_drive_letter=not minimal,
        ), [len(wmi_usb_devices), len(wmi_usb_drives), len(libusb_data)]

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

        drive_path = rf"\\.\PhysicalDrive{device_identifier}"
        h_drive = ct.windll.kernel32.CreateFileW(
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

            data_buffer = ct.create_string_buffer(512)
            sptd.Length = ct.sizeof(SCSI_PASS_THROUGH_DIRECT)
            sptd.CdbLength = 10
            sptd.SenseInfoLength = 32
            sptd.DataIn = SCSI_IOCTL_DATA_IN
            sptd.DataTransferLength = 512
            sptd.TimeOutValue = 5
            sptd.DataBuffer = ct.cast(ct.pointer(data_buffer), ct.c_void_p)
            sptd.SenseInfoOffset = sptd.Length
            ct.memmove(sptd.Cdb, (ct.c_ubyte * 10)(*cdb), 10)

            returned = wintypes.DWORD(0)
            ok = ct.windll.kernel32.DeviceIoControl(
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
            ct.windll.kernel32.CloseHandle(h_drive)

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
                        "serial": (
                            d.DeviceID.split("\\")[-1] if "\\" in d.DeviceID else ""
                        ),
                    }
                )
        return info

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
                    }
                )
        return info

    def _get_apricorn_libusb_data(self):
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
                drives[r.PNPDeviceID.rsplit("\\", 1)[1][:-2]] = int(r.DeviceID[-1:])
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
        for d in wmi_diskdrives or []:
            try:
                idx = int(d.Index)
                if drive_indices and idx not in drive_indices:
                    continue
                escaped = d.DeviceID.replace("\\", "\\\\").replace("'", "\\'")
                letters = []
                for p in self.service.ExecQuery(
                    f"ASSOCIATORS OF {{Win32_DiskDrive.DeviceID='{escaped}'}} WHERE AssocClass = Win32_DiskDriveToDiskPartition"
                ):
                    p_esc = p.DeviceID.replace("\\", "\\\\").replace("'", "\\'")
                    for log_disk in self.service.ExecQuery(
                        f"ASSOCIATORS OF {{Win32_DiskPartition.DeviceID='{p_esc}'}} WHERE AssocClass = Win32_LogicalDiskToPartition"
                    ):
                        letters.append(log_disk.DeviceID)
                mapping[idx] = ", ".join(letters) if letters else "Not Formatted"
            except Exception:
                continue
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
                populate_device_version(
                    int(vid, 16),
                    int(pid, 16),
                    serial,
                    physical_drive_num=drive_num if drive_num != -1 else None,
                )
                if serial
                else {}
            )

            dev_info = UsbDeviceInfo(
                bcdUSB=libusb_data[i]["bcdUSB"],
                idVendor=vid,
                idProduct=pid,
                bcdDevice=libusb_data[i]["bcdDevice"],
                iManufacturer="Apricorn",
                iProduct=wmi_usb_drives[i]["iProduct"],
                iSerial=serial,
                SCSIDevice=scsi,
                driveSizeGB=size_gb,
                mediaType=wmi_usb_drives[i].get("mediaType", "Unknown"),
                **version_info,
            )
            if include_controller:
                setattr(dev_info, "usbController", usb_controllers[i]["ControllerName"])
            setattr(dev_info, "busNumber", libusb_data[i]["bus_number"])
            setattr(dev_info, "deviceAddress", libusb_data[i]["dev_address"])
            setattr(dev_info, "physicalDriveNum", drive_num)
            if include_drive_letter and size_raw != 0.0:
                setattr(
                    dev_info,
                    "driveLetter",
                    drive_letters_map.get(drive_num, "Not Formatted"),
                )
            setattr(dev_info, "readOnly", readonly_map.get(drive_num, False))

            if getattr(dev_info, "scbPartNumber", "N/A") == "N/A":
                for k in (
                    "scbPartNumber",
                    "hardwareVersion",
                    "modelID",
                    "mcuFW",
                    "bridgeFW",
                ):
                    try:
                        delattr(dev_info, k)
                    except AttributeError:
                        pass
            devices.append(dev_info)
        return devices
