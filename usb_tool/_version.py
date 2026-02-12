"""Runtime version resolver for usb_tool."""

from __future__ import annotations

import importlib.metadata
import importlib.resources as resources
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

__all__ = ["get_version"]

PACKAGE_NAME = "apricorn-usb-tool"
CACHE_FILE = Path(__file__).with_name("_cached_version.txt")
_PYPROJECT_VERSION_RE = re.compile(r"^version\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)


def _candidate_roots() -> Iterable[Path]:
    """Yield directories that may contain packaging metadata while avoiding duplicates."""
    module_path = Path(__file__).resolve()
    locations = [
        module_path.parent,
        *module_path.parents,
        Path.cwd(),
    ]
    exe_path = Path(sys.argv[0]).resolve()
    locations.append(exe_path.parent)
    frozen_root = Path(getattr(sys, "_MEIPASS", module_path.parent))
    locations.append(frozen_root)
    seen: set[Path] = set()
    for loc in locations:
        if not isinstance(loc, Path):
            continue
        resolved = loc if loc.is_dir() else loc.parent
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _read_version_from_pkg_info() -> Optional[str]:
    for root in _candidate_roots():
        candidate = root / "usb_tool.egg-info" / "PKG-INFO"
        if not candidate.is_file():
            continue
        try:
            for line in candidate.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            continue
    return None


def _read_version_from_pyproject() -> Optional[str]:
    for root in _candidate_roots():
        candidate = root / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = _PYPROJECT_VERSION_RE.search(text)
        if match:
            return match.group(1).strip()
    return None


def _read_version_resource() -> Optional[str]:
    try:
        data = resources.files("usb_tool").joinpath("_cached_version.txt")
        return data.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    except Exception:
        return None


def _read_cached_version() -> Optional[str]:
    try:
        text = CACHE_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    return _read_version_resource()


def _write_cached_version(version: str) -> None:
    try:
        CACHE_FILE.write_text(version, encoding="utf-8")
    except OSError:
        pass


def get_version(dist_name: str = PACKAGE_NAME) -> str:
    """Return the installed distribution version for display."""
    env_override = os.getenv("USB_TOOL_VERSION")
    if env_override:
        return env_override
    try:
        resolved = importlib.metadata.version(dist_name)
        _write_cached_version(resolved)
        return resolved
    except importlib.metadata.PackageNotFoundError:
        pass
    except Exception:
        pass
    pyproject_version = _read_version_from_pyproject()
    if pyproject_version:
        _write_cached_version(pyproject_version)
        return pyproject_version
    cached = _read_cached_version()
    if cached:
        return cached
    pkg_info_version = _read_version_from_pkg_info()
    if pkg_info_version:
        _write_cached_version(pkg_info_version)
        return pkg_info_version
    return "Unknown"
