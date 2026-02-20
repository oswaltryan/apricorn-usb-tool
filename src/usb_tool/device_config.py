"""Device configuration data for Apricorn USB devices.

This module defines a product-type keyed catalog with customer VID/PID
associations, plus lookup helpers for size normalization.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def _normalize_hex(value: str | None, width: int = 4) -> str:
    if not value:
        return ""
    cleaned = str(value).strip().lower().replace("0x", "")
    return cleaned.zfill(width)


# Size options retained from the legacy PID/bcdDevice mapping for compatibility.
LEGACY_CODE_SIZES: Dict[str, List[int]] = {
    "0310": [256, 500, 1000, 2000, 4000, 8000, 16000],
    "0315": [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000],
    "0351": [128, 256, 500, 1000, 2000, 4000, 8000, 12000, 16000],
    "1400": [256, 500, 1000, 2000, 4000, 8000, 16000],
    "1405": [240, 480, 1000, 2000, 4000],
    "1406": [2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000],
    "1407": [16, 30, 60, 120, 240, 480, 1000, 2000, 4000],
    "1408": [500, 512, 1000, 2000, 4000, 5000, 8000, 16000, 20000],
    "1409": [16, 32, 64, 128, 256, 500, 1000, 2000, 4000],
    "1410": [4, 8, 16, 32, 64, 128, 256, 512],
    "1413": [500, 1000, 2000, 4000],
}


PRODUCT_SIZES: Dict[str, List[int]] = {
    "Padlock": LEGACY_CODE_SIZES["0310"],
    "Padlock 3.0": LEGACY_CODE_SIZES["0310"],
    "Padlock DT": LEGACY_CODE_SIZES["0315"],
    "Padlock DT FIPS": LEGACY_CODE_SIZES["1406"],
    "Padlock SSD": LEGACY_CODE_SIZES["1405"],
    "Padlock NVX": LEGACY_CODE_SIZES["1413"],
    "Fortress": LEGACY_CODE_SIZES["1400"],
    "Fortress L3": LEGACY_CODE_SIZES["1408"],
    "Secure Key 3.0": LEGACY_CODE_SIZES["1407"],
    "Secure Key 3z": LEGACY_CODE_SIZES["1410"],
    # Products without standardized size mapping yet:
    "Secure Key 2.0": [],
    "Padlock Bio": [],
}


# Product catalog sourced from "Apricorn Products VID and PID.csv".
PRODUCTS: Dict[str, Dict[str, object]] = {
    "Fortress": {
        "product_hint": "Fortress",
        "sizes_gb": PRODUCT_SIZES["Fortress"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1400"}],
            "Discover": [{"vid": "0984", "pid": "9a1d"}],
            "Ericsson": [{"vid": "0984", "pid": "1424"}],
            "General Atomics": [{"vid": "0984", "pid": "4732"}],
            "Hyundai": [{"vid": "0984", "pid": "1417"}],
            "United Launch Alliance": [{"vid": "0984", "pid": "047b"}],
        },
    },
    "Fortress L3": {
        "product_hint": "Fortress L3",
        "sizes_gb": PRODUCT_SIZES["Fortress L3"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1408"}],
            "Dominion Resources": [{"vid": "0984", "pid": "1420"}],
            "Ericsson": [{"vid": "0984", "pid": "1425"}],
            "General Electric": [{"vid": "0984", "pid": "5640"}],
            "Honda": [{"vid": "0984", "pid": "1418"}],
            "Sentinel": [{"vid": "230a", "pid": "da36"}],
            "United Launch Alliance": [{"vid": "0984", "pid": "047d"}],
        },
    },
    "Padlock": {
        "product_hint": "Padlock",
        "sizes_gb": PRODUCT_SIZES["Padlock"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "0310"}],
            "Dominion Resources": [{"vid": "0984", "pid": "0311"}],
        },
    },
    "Padlock 3.0": {
        "product_hint": "Padlock 3.0",
        "sizes_gb": PRODUCT_SIZES["Padlock 3.0"],
        "customers": {
            "Bloomberg": [{"vid": "1188", "pid": "9001"}],
            "Morgan-Lewis-Bockis": [{"vid": "0984", "pid": "a9f3"}],
            "UnitedLex": [{"vid": "0984", "pid": "5558"}, {"vid": "0984", "pid": "4745"}],
        },
    },
    "Padlock Bio": {
        "product_hint": "Padlock Bio",
        "sizes_gb": PRODUCT_SIZES["Padlock Bio"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "0340"}],
        },
    },
    "Padlock DT": {
        "product_hint": "Padlock DT",
        "sizes_gb": PRODUCT_SIZES["Padlock DT"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "0315"}],
            "Dominion Resources": [{"vid": "0984", "pid": "0312"}],
            "General Atomics": [{"vid": "0984", "pid": "4733"}],
            "United Launch Alliance": [{"vid": "0984", "pid": "047c"}],
            "UnitedLex": [{"vid": "0984", "pid": "5558"}],
        },
    },
    "Padlock DT FIPS": {
        "product_hint": "Padlock DT FIPS",
        "sizes_gb": PRODUCT_SIZES["Padlock DT FIPS"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1406"}],
            "Discover": [{"vid": "0984", "pid": "9a1c"}],
            "Dominion Resources": [{"vid": "0984", "pid": "14ff"}],
            "Sentinel": [{"vid": "230a", "pid": "da37"}],
        },
    },
    "Padlock NVX": {
        "product_hint": "Padlock NVX",
        "sizes_gb": PRODUCT_SIZES["Padlock NVX"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1413"}],
        },
    },
    "Padlock SSD": {
        "product_hint": "Padlock SSD",
        "sizes_gb": PRODUCT_SIZES["Padlock SSD"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1405"}],
        },
    },
    "Secure Key 2.0": {
        "product_hint": "Secure Key 2.0",
        "sizes_gb": PRODUCT_SIZES["Secure Key 2.0"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "0330"}],
            "Discover": [{"vid": "0984", "pid": "9a1f"}],
        },
    },
    "Secure Key 3.0": {
        "product_hint": "Secure Key 3.0",
        "sizes_gb": PRODUCT_SIZES["Secure Key 3.0"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1407"}],
            "Discover": [{"vid": "0984", "pid": "9a1e"}],
            "Dominion Resources": [{"vid": "0984", "pid": "1422"}, {"vid": "0984", "pid": "0332"}],
            "Harris": [{"vid": "19a5", "pid": "0333"}],
            "Honda": [{"vid": "0984", "pid": "1419"}],
            "Hyundai": [{"vid": "0984", "pid": "1415"}],
        },
    },
    "Secure Key 3z": {
        "product_hint": "Secure Key 3z",
        "sizes_gb": PRODUCT_SIZES["Secure Key 3z"],
        "customers": {
            "Apricorn": [{"vid": "0984", "pid": "1409"}, {"vid": "0984", "pid": "1410"}],
            "Creavo": [{"vid": "0984", "pid": "c7b0"}],
            "Discover": [{"vid": "0984", "pid": "9a10"}],
            "Dominion Resources": [{"vid": "0984", "pid": "1421"}],
            "Ericsson": [{"vid": "0984", "pid": "1426"}],
            "General Atomics": [{"vid": "0984", "pid": "4731"}],
            "Hyundai": [{"vid": "0984", "pid": "1416"}],
            "Ropes and Grey": [{"vid": "0984", "pid": "7a55"}],
            "United Launch Alliance": [{"vid": "0984", "pid": "047a"}],
        },
    },
}


def _build_vid_pid_index(
    products: Dict[str, Dict[str, object]],
) -> Dict[Tuple[str, str], List[str]]:
    index: Dict[Tuple[str, str], List[str]] = {}
    for product, info in products.items():
        customers = info.get("customers", {})
        if not isinstance(customers, dict):
            continue
        for entries in customers.values():
            for entry in entries:
                vid = _normalize_hex(entry.get("vid"))
                pid = _normalize_hex(entry.get("pid"))
                if not vid or not pid:
                    continue
                key = (vid, pid)
                index.setdefault(key, [])
                if product not in index[key]:
                    index[key].append(product)
    return index


VID_PID_INDEX = _build_vid_pid_index(PRODUCTS)
SUPPORTED_VID_PID = set(VID_PID_INDEX.keys())
SUPPORTED_VIDS = {vid for vid, _pid in SUPPORTED_VID_PID}


def get_product_types_for_vid_pid(vid: str | None, pid: str | None) -> List[str]:
    return list(VID_PID_INDEX.get((_normalize_hex(vid), _normalize_hex(pid)), []))


def is_supported_vid_pid(vid: str | None, pid: str | None) -> bool:
    return (_normalize_hex(vid), _normalize_hex(pid)) in SUPPORTED_VID_PID


def is_supported_vid(vid: str | None) -> bool:
    return _normalize_hex(vid) in SUPPORTED_VIDS


def get_size_options(
    vid: str | None, pid: str | None, bcd_device: str | None = None
) -> List[int]:
    sizes: List[int] = []
    for product in get_product_types_for_vid_pid(vid, pid):
        sizes.extend(PRODUCTS[product].get("sizes_gb", []))

    if not sizes:
        sizes = LEGACY_CODE_SIZES.get(_normalize_hex(pid), [])

    if not sizes and bcd_device:
        sizes = LEGACY_CODE_SIZES.get(_normalize_hex(bcd_device), [])

    seen = set()
    deduped = []
    for size in sizes:
        if size in seen:
            continue
        seen.add(size)
        deduped.append(size)
    return deduped


__all__ = [
    "PRODUCTS",
    "VID_PID_INDEX",
    "SUPPORTED_VID_PID",
    "SUPPORTED_VIDS",
    "get_product_types_for_vid_pid",
    "is_supported_vid_pid",
    "is_supported_vid",
    "get_size_options",
]
