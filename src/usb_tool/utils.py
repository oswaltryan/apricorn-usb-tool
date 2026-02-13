# src/usb_tool/utils.py

from __future__ import annotations
from typing import List, Optional


def bytes_to_gb(bytes_value: float) -> float:
    if not isinstance(bytes_value, (int, float)) or bytes_value <= 0:
        return 0.0
    return bytes_value / (1024**3)


def find_closest(target: float, options: List[int]) -> Optional[int]:
    if not isinstance(target, (int, float)) or target <= 0 or not options:
        return None
    try:
        numeric_options = [opt for opt in options if isinstance(opt, (int, float))]
        if not numeric_options:
            return None
        return min(numeric_options, key=lambda x: abs(x - target))
    except (TypeError, ValueError):
        return None


def parse_usb_version(bcd: int) -> str:
    major = (bcd & 0xFF00) >> 8
    minor = (bcd & 0x00F0) >> 4
    subminor = bcd & 0x000F
    return f"{major}.{minor}{subminor}" if subminor else f"{major}.{minor}"
