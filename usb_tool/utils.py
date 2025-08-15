"""Utility helpers shared across platforms."""

from __future__ import annotations

from typing import List, Optional


def bytes_to_gb(bytes_value: float) -> float:
    """Convert a value in bytes to gigabytes.

    Args:
        bytes_value: Byte value to convert.

    Returns:
        The size expressed in gigabytes. Returns ``0.0`` for invalid input.
    """
    if not isinstance(bytes_value, (int, float)) or bytes_value <= 0:
        return 0.0
    return bytes_value / (1024 ** 3)


def find_closest(target: float, options: List[int]) -> Optional[int]:
    """Return the closest option to ``target``.

    Args:
        target: Reference value.
        options: Iterable of numeric options.

    Returns:
        The element of ``options`` nearest to ``target`` or ``None`` if no
        suitable value exists.
    """
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
    """Convert a BCD encoded USB version to a human readable string.

    Args:
        bcd: The binary-coded decimal representation of the version.

    Returns:
        A string such as ``"3.1"``.
    """
    major = (bcd & 0xFF00) >> 8
    minor = (bcd & 0x00F0) >> 4
    subminor = bcd & 0x000F
    return f"{major}.{minor}{subminor}" if subminor else f"{major}.{minor}"

