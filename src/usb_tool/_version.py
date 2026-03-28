"""Runtime version resolver for usb_tool."""

from __future__ import annotations

import importlib.metadata
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

__all__ = ["get_version"]

PACKAGE_NAME = "apricorn-usb-tool"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_FILE_NAME = "pyproject.toml"
PROJECT_SECTION_RE = re.compile(r"(?ms)^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)")
PROJECT_NAME_RE = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']\s*(?:#.*)?$', re.MULTILINE)
PROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*["\']([^"\']+)["\']\s*(?:#.*)?$', re.MULTILINE)


def _module_root_candidates() -> Iterable[Path]:
    seen: set[Path] = set()
    package_dir = PACKAGE_DIR
    trusted_source_dir = Path("src") / "usb_tool"

    for root in package_dir.parents:
        candidate_source_dir = root / trusted_source_dir
        try:
            is_trusted = candidate_source_dir.is_dir() and package_dir.is_relative_to(
                candidate_source_dir
            )
        except ValueError:
            is_trusted = False
        if not is_trusted or root in seen:
            continue
        seen.add(root)
        yield root

    frozen_root_raw = getattr(sys, "_MEIPASS", "")
    if not frozen_root_raw:
        return
    frozen_root = Path(frozen_root_raw).resolve()
    if frozen_root in seen:
        return
    seen.add(frozen_root)
    yield frozen_root


def _parse_pyproject_version(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    project_match = PROJECT_SECTION_RE.search(text)
    if not project_match:
        return None
    body = project_match.group("body")

    name_match = PROJECT_NAME_RE.search(body)
    if not name_match or name_match.group(1).strip() != PACKAGE_NAME:
        return None

    version_match = PROJECT_VERSION_RE.search(body)
    if not version_match:
        return None
    normalized = version_match.group(1).strip()
    if not normalized:
        return None
    return normalized


def _read_repo_pyproject_version() -> str | None:
    for root in _module_root_candidates():
        version = _parse_pyproject_version(root / PROJECT_FILE_NAME)
        if version:
            return version
    return None


def get_version(dist_name: str = PACKAGE_NAME) -> str:
    """Return the installed distribution version for display."""
    env_override = os.getenv("USB_TOOL_VERSION")
    if env_override:
        return env_override
    repo_version = _read_repo_pyproject_version()
    if repo_version:
        return repo_version
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        pass
    except Exception:
        pass
    return "Unknown"
