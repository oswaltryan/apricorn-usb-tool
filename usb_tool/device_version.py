"""Device version query via SCSI READ BUFFER (6).

This module issues a vendor-safe READ BUFFER (opcode 0x3C) with mode 0x01,
host transfer length 1024 bytes, and parses the returned payload into a
best-effort structure. Parsing offsets may need tuning against real devices.

The implementation is self-contained and does not rely on external tools
like sg_raw. It uses per-OS passthrough: SPTI (Windows), SG_IO (Linux), and
DKIO (macOS; may be limited based on permissions/availability).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Callable, Any, cast
import ctypes
import ctypes.util
import os
import errno
import platform
import re


@dataclass
class DeviceVersionInfo:
    scb_part_number: str
    mcu_fw: Tuple[Optional[int], Optional[int], Optional[int]]
    hardware_version: Optional[str] = None
    model_id: Optional[str] = None
    bridge_fw: Optional[str] = None
    raw_data: bytes = b""


SYSTEM = platform.system()


def _build_read_buffer_cdb() -> bytes:
    # READ BUFFER (6) - 0x3C
    # Per request: use CDB bytes [3C, 01, 00, 00, 00, 00], and set host
    # transfer length to 1024 via the OS passthrough layer (not in the CDB).
    return bytes([0x3C, 0x01, 0x00, 0x00, 0x00, 0x00])


# -----------------
# Linux (SG_IO)
# -----------------
if SYSTEM == "Linux":
    # sg.h values
    SG_DXFER_FROM_DEV = -3
    SG_INFO_OK_MASK = 0x1
    SG_INFO_OK = 0x0
    SG_IO = 0x2285

    class SG_IO_HDR(ctypes.Structure):
        _fields_ = [
            ("interface_id", ctypes.c_int),
            ("dxfer_direction", ctypes.c_int),
            ("cmd_len", ctypes.c_ubyte),
            ("mx_sb_len", ctypes.c_ubyte),
            ("iovec_count", ctypes.c_ushort),
            ("dxfer_len", ctypes.c_uint),
            ("dxferp", ctypes.c_void_p),
            ("cmdp", ctypes.c_void_p),
            ("sbp", ctypes.c_void_p),
            ("timeout", ctypes.c_uint),
            ("flags", ctypes.c_uint),
            ("pack_id", ctypes.c_int),
            ("usr_ptr", ctypes.c_void_p),
            ("status", ctypes.c_ubyte),
            ("masked_status", ctypes.c_ubyte),
            ("msg_status", ctypes.c_ubyte),
            ("sb_len_wr", ctypes.c_ubyte),
            ("host_status", ctypes.c_ushort),
            ("driver_status", ctypes.c_ushort),
            ("resid", ctypes.c_int),
            ("duration", ctypes.c_uint),
            ("info", ctypes.c_uint),
        ]

    # Explicit Optional annotations so fallback assignments to None type-check.
    _linux_libc: Optional[ctypes.CDLL]
    _linux_ioctl: Optional[Callable[..., int]]
    try:
        _linux_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        _linux_ioctl = cast(Callable[..., int], _linux_libc.ioctl)
    except Exception:
        _linux_libc = None
        _linux_ioctl = None

    def _linux_read_buffer(device_path: str, timeout_ms: int = 5000) -> bytes:
        if _linux_ioctl is None:
            raise NotImplementedError("libc/ioctl unavailable on Linux")
        fd = -1
        try:
            try:
                fd = os.open(device_path, os.O_RDWR)
            except OSError as e:
                if e.errno == errno.ENOENT:
                    raise FileNotFoundError(device_path)
                if e.errno in (errno.EPERM, errno.EACCES):
                    raise PermissionError(f"Permission denied opening {device_path}")
                raise

            cdb = _build_read_buffer_cdb()
            cdb_buf = (ctypes.c_ubyte * len(cdb))(*cdb)
            data_len = 1024
            data_buf = ctypes.create_string_buffer(data_len)
            sense_buf = ctypes.create_string_buffer(32)

            hdr = SG_IO_HDR()
            ctypes.memset(ctypes.byref(hdr), 0, ctypes.sizeof(hdr))
            hdr.interface_id = ord("S")
            hdr.dxfer_direction = SG_DXFER_FROM_DEV
            hdr.cmd_len = len(cdb)
            hdr.mx_sb_len = ctypes.sizeof(sense_buf)
            hdr.iovec_count = 0
            hdr.dxfer_len = data_len
            hdr.dxferp = ctypes.cast(ctypes.pointer(data_buf), ctypes.c_void_p)
            hdr.cmdp = ctypes.cast(ctypes.pointer(cdb_buf), ctypes.c_void_p)
            hdr.sbp = ctypes.cast(ctypes.pointer(sense_buf), ctypes.c_void_p)
            hdr.timeout = timeout_ms

            ret = _linux_ioctl(fd, SG_IO, ctypes.byref(hdr))
            err = ctypes.get_errno()
            if ret != 0:
                if err in (errno.EPERM, errno.EACCES):
                    raise PermissionError("Permission denied (ioctl SG_IO)")
                raise OSError(err, "ioctl SG_IO failed")

            ok = (
                (hdr.info & SG_INFO_OK_MASK) == SG_INFO_OK
                and hdr.status == 0
                and hdr.host_status == 0
                and hdr.driver_status == 0
            )
            if not ok:
                # Return whatever we got for debugging
                return data_buf.raw[: data_len - max(0, hdr.resid)]
            return data_buf.raw[: data_len - max(0, hdr.resid)]
        finally:
            if fd >= 0:
                os.close(fd)


# -----------------
# Windows (SPTI)
# -----------------
elif SYSTEM == "Windows":
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
            if sptd.ScsiStatus != 0:
                # Return whatever was received (best-effort diagnostics)
                return data_buf.raw
            return data_buf.raw
        finally:
            if h != INVALID_HANDLE_VALUE:
                ctypes.windll.kernel32.CloseHandle(h)


# -----------------
# macOS (DKIO)
# -----------------
elif SYSTEM == "Darwin":
    # Based on a simplified dk_scsi_req structure
    DKIOCSCSIUSERCMD = 0xC050644C
    DK_SCSI_READ = 0x00000001

    class DK_SCSI_REQ(ctypes.Structure):
        _fields_ = [
            ("dsr_cmd", ctypes.c_ubyte * 16),
            ("dsr_cmdlen", ctypes.c_size_t),
            ("dsr_databuf", ctypes.c_void_p),
            ("dsr_datalen", ctypes.c_size_t),
            ("dsr_flags", ctypes.c_uint32),
            ("dsr_timeout", ctypes.c_uint32),
            ("dsr_sense", ctypes.c_ubyte * 32),
            ("dsr_senselen", ctypes.c_uint8),
            ("dsr_status", ctypes.c_uint8),
            ("dsr_resid", ctypes.c_size_t),
        ]

    # Explicit Optional annotations so fallback assignments to None type-check.
    _darwin_libc: Optional[ctypes.CDLL]
    _darwin_ioctl: Optional[Callable[..., int]]
    try:
        _darwin_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        _darwin_ioctl = cast(Callable[..., int], _darwin_libc.ioctl)
    except Exception:
        _darwin_libc = None
        _darwin_ioctl = None

    def _mac_read_buffer(device_path: str, timeout_ms: int = 5000) -> bytes:
        if _darwin_ioctl is None:
            raise NotImplementedError("libc/ioctl unavailable on macOS")
        raw_path = (
            device_path.replace("/dev/disk", "/dev/rdisk", 1)
            if device_path.startswith("/dev/disk")
            else device_path
        )
        fd = -1
        try:
            try:
                fd = os.open(raw_path, os.O_RDWR)
            except OSError as e:
                if e.errno == errno.ENOENT:
                    raise FileNotFoundError(raw_path)
                if e.errno in (errno.EPERM, errno.EACCES):
                    raise PermissionError(f"Permission denied opening {raw_path}")
                raise

            cdb = _build_read_buffer_cdb()
            data_len = 1024
            data_buf = ctypes.create_string_buffer(data_len)

            req = DK_SCSI_REQ()
            ctypes.memset(ctypes.byref(req), 0, ctypes.sizeof(req))
            ctypes.memmove(req.dsr_cmd, (ctypes.c_ubyte * len(cdb))(*cdb), len(cdb))
            req.dsr_cmdlen = len(cdb)
            req.dsr_databuf = ctypes.cast(ctypes.pointer(data_buf), ctypes.c_void_p)
            req.dsr_datalen = data_len
            req.dsr_flags = DK_SCSI_READ
            req.dsr_timeout = timeout_ms
            req.dsr_senselen = ctypes.sizeof(req.dsr_sense)

            ret = _darwin_ioctl(fd, DKIOCSCSIUSERCMD, ctypes.byref(req))
            if ret != 0:
                err = ctypes.get_errno()
                if err in (errno.EPERM, errno.EACCES):
                    raise PermissionError("Permission denied (DKIO ioctl)")
                raise OSError(err, "ioctl DKIOCSCSIUSERCMD failed")
            if req.dsr_status != 0:
                return data_buf.raw[: data_len - int(req.dsr_resid)]
            return data_buf.raw[: data_len - int(req.dsr_resid)]
        finally:
            if fd >= 0:
                os.close(fd)

else:
    # Unsupported OS — provide a stub that raises
    def _unsupported(*_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError(f"Device version query unsupported on {SYSTEM}")


# -----------------
# Public API
# -----------------


def query_device_version(target: str | int, *, timeout: int = 5) -> DeviceVersionInfo:
    """Issue READ BUFFER (6) and parse a best-guess device version structure.

    Linux: ``target`` should be a path like '/dev/sg0'.
    Windows: ``target`` should be a PhysicalDrive number (int).
    macOS: ``target`` should be a disk path like '/dev/diskN'.
    """
    if SYSTEM == "Linux":
        if not (isinstance(target, str) and target.startswith("/dev/sg")):
            raise ValueError("On Linux, target must be an sg device path like /dev/sg0")
        data = _linux_read_buffer(target, timeout_ms=int(timeout * 1000))
    elif SYSTEM == "Windows":
        if not isinstance(target, int):
            raise ValueError(
                "On Windows, target must be an integer PhysicalDrive number"
            )
        data = _windows_read_buffer(target, timeout_sec=timeout)
    elif SYSTEM == "Darwin":
        if not (isinstance(target, str) and target.startswith("/dev/")):
            raise ValueError(
                "On macOS, target must be a disk path like /dev/disk2 or /dev/rdisk2"
            )
        data = _mac_read_buffer(target, timeout_ms=int(timeout * 1000))
    else:
        raise NotImplementedError(f"Unsupported OS: {SYSTEM}")

    info = _parse_payload_best_effort(data)
    info.raw_data = data
    return info


def _parse_payload_best_effort(data: bytes) -> DeviceVersionInfo:
    """Parse the payload to match expected fields without hard-coding values.

    - Bridge FW: bytes[1:3] rendered as two-byte hex (e.g., 0502)
    - SCB Part: first NN-NNNN pattern (e.g., 21-0010)
    - Model IDs: first two digits immediately after the part number
    - Hardware Rev: first two digits immediately after the Model IDs
    - MCU FW: last three digits following the part number, reversed → major.minor.sub
    """
    # Bridge FW: skip any leading printable ASCII, then take the two bytes
    # following the first non-printable header byte. This handles payloads
    # that sometimes start with a printable banner byte.
    bridge_fw: Optional[str] = None
    if data:
        i = 0
        while i < len(data) and 32 <= data[i] <= 126:
            i += 1
        if i + 2 < len(data):
            bridge_fw = f"{data[i+1]:02X}{data[i+2]:02X}"

    # ASCII view for scanning
    ascii_view = "".join(chr(b) if 32 <= b <= 126 else " " for b in data)

    # SCB Part Number: NN-NNNN
    scb_part = ""
    part_match = re.search(r"(\d{2}-\d{4})", ascii_view)
    if part_match:
        scb_part = part_match.group(1)

    # Digits after the SCB part for model IDs and MCU FW
    tail_digits: list[str] = []
    if part_match:
        tail = ascii_view[part_match.end() :]
        tail_digits = re.findall(r"\d", tail)

    # Model IDs: first two digits in tail (in order)
    model_id1: Optional[int] = None
    model_id2: Optional[int] = None
    if part_match and len(tail_digits) >= 2:
        model_id1 = int(tail_digits[1])
        model_id2 = int(tail_digits[0])

    # Hardware rev: take the last two digits immediately preceding the SCB part
    hardware_major: Optional[int] = None
    hardware_minor: Optional[int] = None
    if part_match and len(tail_digits) >= 4:
        hardware_major = int(tail_digits[2])
        hardware_minor = int(tail_digits[3])

    # MCU FW: last three digits in tail, reversed
    mcu_major: Optional[int] = None
    mcu_minor: Optional[int] = None
    mcu_sub: Optional[int] = None
    if len(tail_digits) >= 3:
        mcu_major = int(tail_digits[-1])
        mcu_minor = int(tail_digits[-2])
        mcu_sub = int(tail_digits[-3])

    # Build combined convenience fields
    combined_model_id: Optional[str] = None
    if model_id1 is not None and model_id2 is not None:
        combined_model_id = f"{model_id1}{model_id2}"

    combined_hw_ver: Optional[str] = None
    if hardware_major is not None and hardware_minor is not None:
        # As requested: concatenated order minor+major (e.g., 1 then 2 -> "12")
        combined_hw_ver = f"{hardware_minor}{hardware_major}"

    return DeviceVersionInfo(
        scb_part_number=scb_part,
        mcu_fw=(mcu_major, mcu_minor, mcu_sub),
        hardware_version=combined_hw_ver,
        model_id=combined_model_id,
        bridge_fw=bridge_fw,
    )


__all__ = ["DeviceVersionInfo", "query_device_version"]
