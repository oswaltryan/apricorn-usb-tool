from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import re
import usb.core
import usb.util
import sys
import subprocess
import time


@dataclass
class DeviceVersionInfo:
    scb_part_number: str
    mcu_fw: Tuple[Optional[int], Optional[int], Optional[int]]
    hardware_version: Optional[str] = None
    model_id: Optional[str] = None
    bridge_fw: Optional[str] = None
    raw_data: bytes = b""

def _build_read_buffer_cdb() -> bytes:
    return bytes([0x3C, 0x01, 0x00, 0x00, 0x00, 0x00])

def query_device_version(
    vendor_id: int, product_id: int, serial_number: str, bsd_name: Optional[str] = None
) -> DeviceVersionInfo:
    if sys.platform == "darwin" and bsd_name:
        # On macOS, we must unmount the disk to detach the kernel driver safely
        # and allow pyusb to claim the interface.
        try:
            subprocess.run(
                ["diskutil", "unmountDisk", bsd_name],
                capture_output=True,
                check=False
            )
            # Give the OS a moment to release the device
            time.sleep(1)
        except Exception:
            pass

    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id, serial_number=serial_number)
    if dev is None:
        dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)

    if dev is None:
        raise ValueError("Device not found")


    intf = None
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
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT,
        )
        ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN,
        )

        if ep_out is None or ep_in is None:
            raise ValueError("Could not find IN and OUT endpoints")

        tag = 0x12345678
        data_len = 1024
        cbw = bytearray(31)
        cbw[0:4] = b'USBC'
        cbw[4:8] = tag.to_bytes(4, 'little')
        cbw[8:12] = data_len.to_bytes(4, 'little')
        cbw[12] = 0x80  # IN
        cbw[14] = 6 # CDB length
        cbw[15:21] = _build_read_buffer_cdb()

        try:
            ep_out.write(cbw)
        except usb.core.USBError:
            data = b""
            return

        try:
            response_data = ep_in.read(data_len, timeout=5000)
        except usb.core.USBError:
            response_data = b""

        try:
            ep_in.read(13, timeout=5000)
        except usb.core.USBError:
            pass

        data = response_data.tobytes() if hasattr(response_data, 'tobytes') else b""
    finally:
        if intf is not None:
            usb.util.release_interface(dev, intf)
        try:
            dev.attach_kernel_driver(0)
        except Exception:
            pass

    info = _parse_payload_best_effort(data)
    info.raw_data = data
    
    # Remount on macOS if we unmounted it
    if sys.platform == "darwin" and bsd_name:
        try:
            subprocess.run(
                ["diskutil", "mountDisk", bsd_name],
                capture_output=True,
                check=False
            )
        except Exception:
            pass

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
