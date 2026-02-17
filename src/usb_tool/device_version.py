from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import re


import sys
import subprocess
import time
import ctypes
import errno

# --- Windows Logic ---
if sys.platform == "win32":
    import ctypes.wintypes as wintypes

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x1
    FILE_SHARE_WRITE = 0x2
    OPEN_EXISTING = 0x3
    INVALID_HANDLE_VALUE = -1
    IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014

    class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("ScsiStatus", wintypes.BYTE),
            ("PathId", wintypes.BYTE),
            ("TargetId", wintypes.BYTE),
            ("Lun", wintypes.BYTE),
            ("CdbLength", wintypes.BYTE),
            ("SenseInfoLength", wintypes.BYTE),
            ("DataIn", wintypes.BYTE),
            ("DataTransferLength", wintypes.ULONG),
            ("TimeOutValue", wintypes.ULONG),
            ("DataBuffer", ctypes.c_void_p),
            ("SenseInfoOffset", wintypes.ULONG),
            ("Cdb", wintypes.BYTE * 16),
        ]

    class SPTD_WITH_SENSE(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("sptd", SCSI_PASS_THROUGH_DIRECT),
            ("ucSenseBuf", ctypes.c_ubyte * 32),
        ]

    def _build_read_buffer_cdb() -> bytes:
        # READ BUFFER (6) - 0x3C
        return bytes([0x3C, 0x01, 0x00, 0x00, 0x00, 0x00])

    def _windows_read_buffer(physical_drive_num: int, timeout_sec: int = 5) -> bytes:
        drive_path = rf"\\.\PhysicalDrive{physical_drive_num}"
        h = INVALID_HANDLE_VALUE
        try:
            h = ctypes.windll.kernel32.CreateFileW(
                drive_path,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if h == INVALID_HANDLE_VALUE:
                win_error = ctypes.GetLastError()
                if win_error == errno.EACCES:
                    raise PermissionError("Administrator privileges required")
                raise ctypes.WinError(win_error)

            cdb = _build_read_buffer_cdb()
            data_len = 1024
            data_buf = ctypes.create_string_buffer(data_len)
            sptd_sense = SPTD_WITH_SENSE()
            ctypes.memset(ctypes.byref(sptd_sense), 0, ctypes.sizeof(sptd_sense))
            sptd = sptd_sense.sptd
            sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
            sptd.PathId = 0
            sptd.TargetId = 0
            sptd.Lun = 0
            sptd.CdbLength = len(cdb)
            sptd.SenseInfoLength = len(sptd_sense.ucSenseBuf)
            sptd.DataIn = 1  # DATA_IN
            sptd.DataTransferLength = data_len
            sptd.TimeOutValue = int(timeout_sec)
            sptd.DataBuffer = ctypes.cast(ctypes.pointer(data_buf), ctypes.c_void_p)
            sptd.SenseInfoOffset = sptd.Length
            ctypes.memmove(sptd.Cdb, (ctypes.c_ubyte * len(cdb))(*cdb), len(cdb))

            returned_bytes = wintypes.DWORD(0)
            ok = ctypes.windll.kernel32.DeviceIoControl(
                h,
                IOCTL_SCSI_PASS_THROUGH_DIRECT,
                ctypes.byref(sptd_sense),
                ctypes.sizeof(sptd_sense),
                ctypes.byref(sptd_sense),
                ctypes.sizeof(sptd_sense),
                ctypes.byref(returned_bytes),
                None,
            )
            if ok == 0:
                raise ctypes.WinError(ctypes.GetLastError())
            # We return the data buffer regardless of ScsiStatus to support OOB mode
            return data_buf.raw
        finally:
            if h != INVALID_HANDLE_VALUE:
                ctypes.windll.kernel32.CloseHandle(h)


@dataclass
class DeviceVersionInfo:
    scb_part_number: str
    mcu_fw: Tuple[Optional[int], Optional[int], Optional[int]]
    hardware_version: Optional[str] = None
    model_id: Optional[str] = None
    bridge_fw: Optional[str] = None
    raw_data: bytes = b""


def _query_usb_core(
    vendor_id: int, product_id: int, serial_number: str, bsd_name: Optional[str] = None
) -> bytes:
    # Ensure usb modules are available
    try:
        import usb.core
        import usb.util
    except ImportError:
        # If pyusb isn't available, we can't use this method.
        # This is expected on minimized Windows builds.
        return b""

    if sys.platform == "darwin" and bsd_name:
        # On macOS, we must unmount the disk to detach the kernel driver safely
        # and allow pyusb to claim the interface.
        try:
            subprocess.run(
                ["diskutil", "unmountDisk", bsd_name], capture_output=True, check=False
            )
            # Give the OS a moment to release the device
            time.sleep(1)
        except Exception:
            pass

    dev = usb.core.find(
        idVendor=vendor_id, idProduct=product_id, serial_number=serial_number
    )
    if dev is None:
        dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)

    if dev is None:
        raise ValueError("Device not found")

    intf = None
    data = b""
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass

    try:
        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]

        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            ),
        )
        ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            ),
        )

        if ep_out is None or ep_in is None:
            raise ValueError("Could not find IN and OUT endpoints")

        tag = 0x12345678
        data_len = 1024
        cbw = bytearray(31)
        cbw[0:4] = b"USBC"
        cbw[4:8] = tag.to_bytes(4, "little")
        cbw[8:12] = data_len.to_bytes(4, "little")
        cbw[12] = 0x80  # IN
        cbw[14] = 6  # CDB length
        # Using the same CDB construction
        cbw[15:21] = bytes([0x3C, 0x01, 0x00, 0x00, 0x00, 0x00])

        try:
            ep_out.write(cbw)
        except usb.core.USBError:
            return b""

        try:
            response_data = ep_in.read(data_len, timeout=5000)
        except usb.core.USBError:
            response_data = b""

        try:
            ep_in.read(13, timeout=5000)
        except usb.core.USBError:
            pass

        data = response_data.tobytes() if hasattr(response_data, "tobytes") else b""
    finally:
        if intf is not None:
            usb.util.release_interface(dev, intf)
        try:
            dev.attach_kernel_driver(0)
        except Exception:
            pass

    # Remount on macOS if we unmounted it
    if sys.platform == "darwin" and bsd_name:
        try:
            subprocess.run(
                ["diskutil", "mountDisk", bsd_name], capture_output=True, check=False
            )
        except Exception:
            pass

    return data


def query_device_version(
    vendor_id: int,
    product_id: int,
    serial_number: str,
    bsd_name: Optional[str] = None,
    physical_drive_num: Optional[int] = None,
) -> DeviceVersionInfo:
    data = b""

    # Try Windows SPTI first if index is provided
    if sys.platform == "win32" and physical_drive_num is not None:
        try:
            data = _windows_read_buffer(physical_drive_num)
        except Exception:
            # Fallback or just empty
            data = b""
    else:
        # Fallback to libusb (macOS/Linux)
        try:
            data = _query_usb_core(vendor_id, product_id, serial_number, bsd_name)
        except Exception:
            data = b""

    info = _parse_payload_best_effort(data)
    info.raw_data = data
    return info


def _parse_payload_best_effort(data: bytes) -> DeviceVersionInfo:
    """Parse the payload to match expected fields for Apricorn devices."""
    bridge_fw: Optional[str] = None
    scb_part: str = ""
    mcu_fw: Tuple[Optional[int], Optional[int], Optional[int]] = (None, None, None)
    hw_ver: Optional[str] = None
    model_id: Optional[str] = None

    if data and len(data) >= 4:
        bridge_fw = f"{data[2]:02X}{data[3]:02X}"

    match = re.search(rb"(\d{2})-(\d{11})", data)

    if match:
        try:
            prefix_str = match.group(1).decode("ascii")
            body_str = match.group(2).decode("ascii")
            scb_part = f"{prefix_str}-{body_str[:4]}"
            if len(body_str) >= 11:
                model_id = f"{body_str[4]}{body_str[5]}"
                hw_ver = f"{body_str[6]}{body_str[7]}"
                mj = int(body_str[10])
                mn = int(body_str[9])
                sb = int(body_str[8])
                mcu_fw = (mj, mn, sb)
        except (ValueError, IndexError):
            pass

    return DeviceVersionInfo(
        scb_part_number=scb_part if scb_part else "N/A",
        mcu_fw=mcu_fw,
        hardware_version=hw_ver,
        model_id=model_id,
        bridge_fw=bridge_fw,
    )


__all__ = ["DeviceVersionInfo", "query_device_version"]
