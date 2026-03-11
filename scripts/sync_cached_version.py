from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CACHE_FILE = ROOT / "src" / "usb_tool" / "_cached_version.txt"
VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise RuntimeError(f"Could not find project version in {PYPROJECT}")
    return match.group(1).strip()


def main() -> int:
    version = _read_pyproject_version()
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
