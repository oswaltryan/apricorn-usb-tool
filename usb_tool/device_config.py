"""Device configuration data for Apricorn USB devices.

This module centralizes the mapping of Apricorn USB product identifiers to
human-readable product hints and their available storage sizes in gigabytes.
Each key is a four-character lowercase hexadecimal string representing either
a PID or bcdDevice value. The value is a list containing the product name hint
and a list of supported capacities.
"""

from typing import Dict, List, Tuple

# PID or bcdDevice: [Product Name Hint, [Sizes in GB]]
# Ensure identifiers are lowercase hex strings without the 0x prefix
closest_values: Dict[str, Tuple[str, List[int]]] = {
    "0310": ("Padlock 3.0", [256, 500, 1000, 2000, 4000, 8000, 16000]),
    "0315": (
        "Padlock DT",
        [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000],
    ),
    "0351": ("Aegis Portable", [128, 256, 500, 1000, 2000, 4000, 8000, 12000, 16000]),
    "1400": ("Fortress", [256, 500, 1000, 2000, 4000, 8000, 16000]),
    "1405": ("Padlock SSD", [240, 480, 1000, 2000, 4000]),
    "1406": (
        "Padlock DT FIPS",
        [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000],
    ),
    "1407": ("Secure Key 3.0", [16, 30, 60, 120, 240, 480, 1000, 2000, 4000]),
    "1408": ("Fortress L3", [500, 512, 1000, 2000, 4000, 5000, 8000, 16000, 20000]),
    "1409": (
        "Secure Key 3.0",
        [16, 32, 64, 128, 256, 500, 1000, 2000, 4000],
    ),  # Combined ASK 3NXC / 3NX
    "1410": ("Secure Key 3Z", [4, 8, 16, 32, 64, 128, 256, 512]),
    "1413": ("Padlock NVX", [500, 1000, 2000, 4000]),
}

__all__ = ["closest_values"]
