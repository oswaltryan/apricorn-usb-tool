#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Filename: scsi_read10_util.py
# Description: Provides a cross-platform function to send a single SCSI READ(10) command.
# Designed for direct import into other Python projects.

import argparse
import ctypes
import ctypes.util
import sys
import os
import platform
import struct
import errno
import time # Used only in example

# --- Platform Specific Setup ---
_SYSTEM = platform.system()

# --- Constants ---
# SCSI Opcodes
SCSI_READ_10 = 0x28

# --- Custom Exception ---
class ScsiError(Exception):
    """Custom exception for SCSI command failures."""
    def __init__(self, message, scsi_status=None, sense_data=None, os_errno=None, driver_status=None, host_status=None):
        super().__init__(message)
        self.scsi_status = scsi_status
        self.sense_data = sense_data
        self.os_errno = os_errno
        self.driver_status = driver_status # Linux specific
        self.host_status = host_status     # Linux specific
        self.sense_hex = sense_data.hex() if sense_data else "N/A"

    def __str__(self):
        details = [super().__str__()]
        if self.scsi_status is not None:
            details.append(f"SCSI Status: 0x{self.scsi_status:02X}")
        if self.sense_data:
            details.append(f"Sense: {self.sense_hex}")
        if self.os_errno is not None:
             details.append(f"OS Errno: {self.os_errno} ({os.strerror(self.os_errno)})")
        if self.driver_status is not None:
             details.append(f"Driver Status: 0x{self.driver_status:02X}")
        if self.host_status is not None:
             details.append(f"Host Status: 0x{self.host_status:02X}")
        return " ".join(details)

# --- Windows Specific ---
if _SYSTEM == "Windows":
    import ctypes.wintypes as wintypes
    # Windows API Constants
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x1
    FILE_SHARE_WRITE = 0x2
    OPEN_EXISTING = 0x3
    INVALID_HANDLE_VALUE = -1
    IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
    SCSI_IOCTL_DATA_IN = 1

    # Windows Structures
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
            ("TimeOutValue", wintypes.ULONG), # Seconds
            ("DataBuffer", ctypes.c_void_p),
            ("SenseInfoOffset", wintypes.ULONG),
            ("Cdb", wintypes.BYTE * 16),
        ]

    class SPTD_WITH_SENSE(ctypes.Structure):
        _pack_ = 1 # Important for alignment
        _fields_ = [
            ("sptd", SCSI_PASS_THROUGH_DIRECT),
            ("ucSenseBuf", ctypes.c_ubyte * 32) # Sense buffer
        ]

# --- Linux Specific ---
elif _SYSTEM == "Linux":
    # Linux Constants (from headers like <fcntl.h>, <scsi/sg.h>)
    O_RDWR = os.O_RDWR
    SG_DXFER_NONE = -1
    SG_DXFER_TO_DEV = -2
    SG_DXFER_FROM_DEV = -3
    SG_INFO_OK_MASK = 0x1
    SG_INFO_OK = 0x0 # Must match mask
    SG_IO = 0x2285 # From <scsi/sg.h>, verify this value if needed

    # Linux sg_io_hdr structure (adjust field types/sizes for 32/64 bit if necessary)
    # Using c_void_p for pointers makes it more portable between 32/64 bit.
    class SG_IO_HDR(ctypes.Structure):
        _fields_ = [
            ("interface_id", ctypes.c_int),
            ("dxfer_direction", ctypes.c_int),
            ("cmd_len", ctypes.c_ubyte),
            ("mx_sb_len", ctypes.c_ubyte),
            ("iovec_count", ctypes.c_ushort),
            ("dxfer_len", ctypes.c_uint),
            ("dxferp", ctypes.c_void_p),    # Buffer for data transfer
            ("cmdp", ctypes.c_void_p),      # SCSI command (CDB)
            ("sbp", ctypes.c_void_p),       # Sense buffer
            ("timeout", ctypes.c_uint),     # Milliseconds
            ("flags", ctypes.c_uint),
            ("pack_id", ctypes.c_int),
            ("usr_ptr", ctypes.c_void_p),
            ("status", ctypes.c_ubyte),     # SCSI status
            ("masked_status", ctypes.c_ubyte),
            ("msg_status", ctypes.c_ubyte),
            ("sb_len_wr", ctypes.c_ubyte),  # Actual sense length written
            ("host_status", ctypes.c_ushort),
            ("driver_status", ctypes.c_ushort),
            ("resid", ctypes.c_int),
            ("duration", ctypes.c_uint),
            ("info", ctypes.c_uint)
        ]

    # Load libc
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
    except OSError:
        raise ImportError("Could not load libc.")
    ioctl = libc.ioctl

# --- macOS Specific ---
elif _SYSTEM == "Darwin":
    # macOS Constants (mostly from <sys/fcntl.h>, <sys/ioctl.h>, <IOKit/storage/IODVDTypes.h>, <sys/dkio.h>)
    O_RDWR = os.O_RDWR
    # _IOWR('d', 76, struct dk_scsi_req) - calculate or find value
    # Found commonly used value: 0xC050644C (may vary slightly)
    DKIOCSCSIUSERCMD = 0xC050644C
    DK_SCSI_READ = 0x00000001 # Flag for read direction
    DK_SCSI_WRITE = 0x00000002 # Flag for write direction

    # macOS Structure (dk_scsi_req or similar - simplified definition)
    # Based on common examples, exact definition might vary.
    # Using fixed-size arrays for buffers here.
    class DK_SCSI_REQ(ctypes.Structure):
        _fields_ = [
            ("dsr_cmd", ctypes.c_ubyte * 16),   # CDB
            ("dsr_cmdlen", ctypes.c_size_t),
            ("dsr_databuf", ctypes.c_void_p),   # Pointer to data buffer
            ("dsr_datalen", ctypes.c_size_t),   # Expected data length
            ("dsr_flags", ctypes.c_uint32),     # Direction flags etc.
            ("dsr_timeout", ctypes.c_uint32),   # Milliseconds
            ("dsr_sense", ctypes.c_ubyte * 32), # Sense buffer
            ("dsr_senselen", ctypes.c_uint8),   # Max sense len
            ("dsr_status", ctypes.c_uint8),     # SCSI status
            ("dsr_resid", ctypes.c_size_t)      # Residual data length
        ]

    # Load libc
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
    except OSError:
        raise ImportError("Could not load libc.")
    ioctl = libc.ioctl

else:
    # Unsupported OS
    pass # send_scsi_read10 will check _SYSTEM later

def _build_read10_cdb(lba=0, blocks=1):
    """Builds the 10-byte CDB for SCSI READ(10)."""
    cdb = [0] * 10
    cdb[0] = SCSI_READ_10
    # LBA (Bytes 2-5, Big-Endian)
    cdb[2] = (lba >> 24) & 0xFF
    cdb[3] = (lba >> 16) & 0xFF
    cdb[4] = (lba >> 8) & 0xFF
    cdb[5] = lba & 0xFF
    # Transfer Length in Blocks (Bytes 7-8, Big-Endian)
    cdb[7] = (blocks >> 8) & 0xFF
    cdb[8] = blocks & 0xFF
    return cdb

# --- Internal Platform Implementations ---


def _windows_read10(drive_num, lba, blocks, block_size, timeout_sec, path_id, target_id, lun):
    drive_path = rf"\\.\PhysicalDrive{drive_num}"
    h_drive = INVALID_HANDLE_VALUE

    try:
        h_drive = ctypes.windll.kernel32.CreateFileW(
            drive_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )
        if h_drive == INVALID_HANDLE_VALUE:
            win_error = ctypes.GetLastError()
            # Raise ctypes.WinError - this IS an OSError subclass
            # It automatically formats the message based on the error code.
            raise ctypes.WinError(win_error)

        sptd_sense = SPTD_WITH_SENSE()
        ctypes.memset(ctypes.byref(sptd_sense), 0, ctypes.sizeof(sptd_sense))
        sptd = sptd_sense.sptd
        sense_buffer = sptd_sense.ucSenseBuf

        # Build CDB
        cdb = _build_read10_cdb(lba, blocks)
        cdb_len = len(cdb)
        buffer_size = blocks * block_size
        data_buffer = ctypes.create_string_buffer(buffer_size)

        # Setup SPTD structure
        sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
        sptd.PathId = path_id
        sptd.TargetId = target_id
        sptd.Lun = lun
        sptd.CdbLength = cdb_len
        sptd.SenseInfoLength = len(sense_buffer)
        sptd.DataIn = SCSI_IOCTL_DATA_IN
        sptd.DataTransferLength = buffer_size
        sptd.TimeOutValue = timeout_sec
        sptd.DataBuffer = ctypes.cast(ctypes.pointer(data_buffer), ctypes.c_void_p)
        sptd.SenseInfoOffset = sptd.Length # Sense buffer follows immediately in our combined struct

        ctypes.memmove(sptd.Cdb, (ctypes.c_ubyte * cdb_len)(*cdb), cdb_len)

        returned_bytes_struct = wintypes.DWORD(0)
        status = ctypes.windll.kernel32.DeviceIoControl(
            h_drive, IOCTL_SCSI_PASS_THROUGH_DIRECT,
            ctypes.byref(sptd_sense), ctypes.sizeof(sptd_sense),
            ctypes.byref(sptd_sense), ctypes.sizeof(sptd_sense),
            ctypes.byref(returned_bytes_struct), None
        )

        sense_data_bytes = bytes(sense_buffer[:sptd.SenseInfoLength])

        if status == 0:
            win_error = ctypes.GetLastError()
            # Also raise WinError here for consistency
            raise ctypes.WinError(win_error)

        if sptd.ScsiStatus == 0x00:
            return data_buffer.raw[:returned_bytes_struct.value]
        else:
            raise ScsiError("SCSI command READ(10) failed", sptd.ScsiStatus, sense_data_bytes)

    finally:
        if h_drive != INVALID_HANDLE_VALUE:
            ctypes.windll.kernel32.CloseHandle(h_drive)


def _linux_read10(device_path, lba, blocks, block_size, timeout_ms):
    fd = -1
    try:
        fd = os.open(device_path, O_RDWR)
        if fd < 0:
             # This might also indicate permission error
             raise OSError(f"Failed to open device {device_path}")

        # Prepare buffers and structures
        cdb = _build_read10_cdb(lba, blocks)
        cdb_len = len(cdb)
        buffer_size = blocks * block_size
        data_buffer = ctypes.create_string_buffer(buffer_size)
        sense_buffer = ctypes.create_string_buffer(32) # Recommended sense size
        cdb_buffer = (ctypes.c_ubyte * cdb_len)(*cdb)

        sg_hdr = SG_IO_HDR()
        ctypes.memset(ctypes.byref(sg_hdr), 0, ctypes.sizeof(sg_hdr))

        sg_hdr.interface_id = ord('S') # Standard 'S' for SCSI generic
        sg_hdr.dxfer_direction = SG_DXFER_FROM_DEV
        sg_hdr.cmd_len = cdb_len
        sg_hdr.mx_sb_len = ctypes.sizeof(sense_buffer)
        sg_hdr.iovec_count = 0 # Not using iovec
        sg_hdr.dxfer_len = buffer_size
        sg_hdr.dxferp = ctypes.cast(ctypes.pointer(data_buffer), ctypes.c_void_p)
        sg_hdr.cmdp = ctypes.cast(ctypes.pointer(cdb_buffer), ctypes.c_void_p)
        sg_hdr.sbp = ctypes.cast(ctypes.pointer(sense_buffer), ctypes.c_void_p)
        sg_hdr.timeout = timeout_ms # Timeout in milliseconds

        # Send IOCTL
        ret = ioctl(fd, SG_IO, ctypes.byref(sg_hdr))
        current_errno = ctypes.get_errno()

        if ret != 0:
             # Check errno for specifics
             if current_errno == errno.EPERM or current_errno == errno.EACCES:
                 raise PermissionError(f"Permission denied for ioctl on {device_path}. Requires root or disk group.")
             raise OSError(f"ioctl(SG_IO) failed on {device_path}. Errno: {current_errno} ({os.strerror(current_errno)})", None, None, current_errno)

        # Check SCSI status and other statuses from sg_hdr
        # See sg_io_v3 documentation for status interpretation
        ok = (
              (sg_hdr.info & SG_INFO_OK_MASK) == SG_INFO_OK and
              sg_hdr.host_status == 0 and
              sg_hdr.driver_status == 0
        )

        sense_data_bytes = sense_buffer.raw[:sg_hdr.sb_len_wr]

        if ok and sg_hdr.status == 0x00:
            # Calculate actual data transferred (total - residual)
            bytes_returned = buffer_size - sg_hdr.resid
            return data_buffer.raw[:bytes_returned]
        else:
             raise ScsiError(
                 "SCSI command READ(10) failed (Linux SG_IO)",
                 scsi_status=sg_hdr.status,
                 sense_data=sense_data_bytes,
                 driver_status=sg_hdr.driver_status,
                 host_status=sg_hdr.host_status
             )

    finally:
        if fd >= 0:
            os.close(fd)


def _macos_read10(device_path, lba, blocks, block_size, timeout_ms):
    # macOS often requires the raw device path
    if device_path.startswith("/dev/disk"):
        raw_device_path = device_path.replace("/dev/disk", "/dev/rdisk", 1)
    else:
        raw_device_path = device_path # Assume user provided raw path if not standard /dev/disk

    fd = -1
    try:
        fd = os.open(raw_device_path, O_RDWR)
        if fd < 0:
            raise OSError(f"Failed to open raw device {raw_device_path}")

        # Prepare buffers and structure
        cdb = _build_read10_cdb(lba, blocks)
        cdb_len = len(cdb)
        buffer_size = blocks * block_size
        data_buffer = ctypes.create_string_buffer(buffer_size)

        dk_req = DK_SCSI_REQ()
        ctypes.memset(ctypes.byref(dk_req), 0, ctypes.sizeof(dk_req))

        # Populate DK_SCSI_REQ
        ctypes.memmove(dk_req.dsr_cmd, (ctypes.c_ubyte * cdb_len)(*cdb), cdb_len)
        dk_req.dsr_cmdlen = cdb_len
        dk_req.dsr_databuf = ctypes.cast(ctypes.pointer(data_buffer), ctypes.c_void_p)
        dk_req.dsr_datalen = buffer_size
        dk_req.dsr_flags = DK_SCSI_READ # Direction: Read
        dk_req.dsr_timeout = timeout_ms # Timeout in milliseconds
        dk_req.dsr_senselen = ctypes.sizeof(dk_req.dsr_sense) # Max sense length

        # Send IOCTL
        ret = ioctl(fd, DKIOCSCSIUSERCMD, ctypes.byref(dk_req))
        current_errno = ctypes.get_errno()

        if ret != 0:
            if current_errno == errno.EPERM or current_errno == errno.EACCES:
                raise PermissionError(f"Permission denied for ioctl on {raw_device_path}. Requires root.")
            raise OSError(f"ioctl(DKIOCSCSIUSERCMD) failed on {raw_device_path}. Errno: {current_errno} ({os.strerror(current_errno)})", None, None, current_errno)

        # Check SCSI status
        sense_data_bytes = bytes(dk_req.dsr_sense[:dk_req.dsr_senselen]) # Use actual length if available (check header def)

        if dk_req.dsr_status == 0x00:
            bytes_returned = buffer_size - dk_req.dsr_resid
            return data_buffer.raw[:bytes_returned]
        else:
            raise ScsiError("SCSI command READ(10) failed (macOS DKIOCSCSIUSERCMD)",
                            scsi_status=dk_req.dsr_status,
                            sense_data=sense_data_bytes)

    finally:
        if fd >= 0:
            os.close(fd)


# --- Public Cross-Platform Function ---
def send_scsi_read10(device_identifier, lba=0, blocks=1, block_size=512, timeout=5):
    """
    Sends a single SCSI READ(10) command to the specified device (cross-platform).

    Args:
        device_identifier (int or str):
            - Windows: Integer physical drive number (e.g., 0, 1).
            - Linux: String block device path (e.g., '/dev/sda').
            - macOS: String disk device path (e.g., '/dev/disk2').
        lba (int): The starting Logical Block Address. Defaults to 0.
        blocks (int): The number of blocks to read. Defaults to 1.
        block_size (int): The expected size of a block in bytes. Defaults to 512.
        timeout (int): Command timeout in seconds. Defaults to 5.

    Returns:
        bytes: The raw data read from the drive upon success.

    Raises:
        ValueError: If input parameters (blocks, block_size) are invalid or device_identifier type is wrong for OS.
        PermissionError: If the script lacks Administrator/root privileges.
        FileNotFoundError: If the specified device path does not exist (Linux/macOS).
        OSError: If opening the device or the IOCTL call fails at the OS level.
        ScsiError: If the SCSI command completes with a non-zero status.
        NotImplementedError: If run on an unsupported operating system.
        Exception: For other unexpected errors.
    """
    if blocks <= 0 or block_size <= 0:
        raise ValueError("Number of blocks and block_size must be positive.")

    timeout_ms = int(timeout * 1000) # Convert timeout to milliseconds for Linux/macOS

    if _SYSTEM == "Windows":
        if not isinstance(device_identifier, int):
            raise ValueError("On Windows, device_identifier must be an integer drive number.")
        # Assuming PathId=0, TargetId=0, Lun=0 which works for most USB drives
        return _windows_read10(device_identifier, lba, blocks, block_size, timeout, 0, 0, 0)

    elif _SYSTEM == "Linux":
        if not isinstance(device_identifier, str):
            raise ValueError("On Linux, device_identifier must be a string device path (e.g., '/dev/sda').")
        if not os.path.exists(device_identifier):
             raise FileNotFoundError(f"Device path not found: {device_identifier}")
        return _linux_read10(device_identifier, lba, blocks, block_size, timeout_ms)

    elif _SYSTEM == "Darwin":
        if not isinstance(device_identifier, str):
            raise ValueError("On macOS, device_identifier must be a string device path (e.g., '/dev/disk2').")
        # Basic check for existence, actual raw path checked in implementation
        if not os.path.exists(device_identifier) and not os.path.exists(device_identifier.replace("/dev/disk", "/dev/rdisk", 1)):
             raise FileNotFoundError(f"Device path not found: {device_identifier}")
        return _macos_read10(device_identifier, lba, blocks, block_size, timeout_ms)

    else:
        raise NotImplementedError(f"SCSI pass-through not implemented for operating system: {_SYSTEM}")


# --- Example Usage ---
if __name__ == "__main__":
    print(f"Running SCSI READ(10) Utility Example on {_SYSTEM}...")

    parser = argparse.ArgumentParser(description="Test Cross-Platform SCSI READ(10) Utility")
    parser.add_argument("device", help="Device identifier (Drive number for Windows, /dev/path for Linux/macOS)")
    parser.add_argument("--lba", type=int, default=0)
    parser.add_argument("--blocks", type=int, default=1)
    parser.add_argument("--blocksize", type=int, default=512)
    parser.add_argument("--timeout", type=int, default=5)
    test_args = parser.parse_args()

    # Convert device identifier type based on OS for the function call
    if _SYSTEM == "Windows":
        try:
            device_id = int(test_args.device)
        except ValueError:
            print("ERROR: On Windows, device must be an integer drive number.")
            sys.exit(1)
    else:
        device_id = test_args.device # Keep as string for Linux/macOS


    # Check privileges (best effort)
    has_perms = False
    if _SYSTEM == "Windows":
        try: has_perms = (ctypes.windll.shell32.IsUserAnAdmin() != 0)
        except AttributeError: pass # Ignore if function doesn't exist
    elif _SYSTEM == "Linux" or _SYSTEM == "Darwin":
        try: has_perms = (os.geteuid() == 0)
        except AttributeError: pass # Ignore if function doesn't exist

    if not has_perms:
        print("\nWARNING: Example run may fail without Administrator/root privileges.")

    start_time = time.time()
    try:
        print(f"\nAttempting to read {test_args.blocks} block(s) from LBA {test_args.lba} on device '{device_id}'...")

        read_data = send_scsi_read10(
            device_identifier=device_id,
            lba=test_args.lba,
            blocks=test_args.blocks,
            block_size=test_args.blocksize,
            timeout=test_args.timeout
        )

        end_time = time.time()
        print("\nCommand SUCCEEDED.")
        print(f"Read {len(read_data)} bytes in {end_time - start_time:.3f} seconds.")
        if read_data:
             print(f"First 64 bytes (hex): {read_data[:64].hex()}")

    except (PermissionError, FileNotFoundError, OSError, ValueError, ScsiError, NotImplementedError) as e:
        end_time = time.time()
        print(f"\nERROR during test run ({end_time - start_time:.3f}s): {e}")
    except Exception as e:
        end_time = time.time()
        print(f"\nUNEXPECTED ERROR during test run ({end_time - start_time:.3f}s): {e}")
        import traceback
        traceback.print_exc()