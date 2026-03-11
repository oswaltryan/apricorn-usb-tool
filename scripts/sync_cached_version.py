from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CACHE_FILE = ROOT / "src" / "usb_tool" / "_cached_version.txt"
VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _read_pyproject_version(path: Path = PYPROJECT) -> str:
    text = path.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise RuntimeError(f"Could not find project version in {path}")
    return match.group(1).strip()


def _read_head_file(path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise RuntimeError(
            "Version auto-bump requires dotted numeric versions like '1.4.0'"
        )
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def _read_pyproject_version_from_text(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise RuntimeError("Could not find project version in HEAD pyproject.toml")
    return match.group(1).strip()


def _resolve_target_version() -> str:
    current_base = _read_pyproject_version()
    head_base_text = _read_head_file("pyproject.toml")
    head_cached = _read_head_file("src/usb_tool/_cached_version.txt")

    if not head_base_text or not head_cached:
        return current_base

    head_base = _read_pyproject_version_from_text(head_base_text)
    if head_base != current_base:
        return current_base

    major, minor, patch = _parse_version(head_cached)
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    version = _resolve_target_version()
    expected = f"{version}\n"
    current = ""
    try:
        current = CACHE_FILE.read_text(encoding="utf-8")
    except OSError:
        pass

    if current == expected:
        return 0

    CACHE_FILE.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Updated {CACHE_FILE.relative_to(ROOT)} to {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
