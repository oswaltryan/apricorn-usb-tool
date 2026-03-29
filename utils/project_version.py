from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PROJECT_NAME = "apricorn-usb-tool"
PROJECT_SECTION_RE = re.compile(r"(?ms)^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)")
PROJECT_NAME_RE = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']\s*(?:#.*)?$', re.MULTILINE)
PROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*["\']([^"\']+)["\']\s*(?:#.*)?$', re.MULTILINE)
VERSION_LINE_RE = re.compile(
    r'^(?P<prefix>\s*version\s*=\s*["\'])(?P<value>[^"\']+)(?P<suffix>["\']\s*(?:#.*)?)$',
    re.MULTILINE,
)


def _resolve_pyproject_path(path: Path | None = None) -> Path:
    return path or PYPROJECT


def _load_pyproject_text(path: Path | None = None) -> str:
    resolved = _resolve_pyproject_path(path)
    return resolved.read_text(encoding="utf-8")


def _parse_project_name_and_version(text: str) -> tuple[str, str]:
    project_match = PROJECT_SECTION_RE.search(text)
    if not project_match:
        raise RuntimeError("Missing [project] table in pyproject.toml")

    body = project_match.group("body")
    name_match = PROJECT_NAME_RE.search(body)
    if not name_match:
        raise RuntimeError("Missing [project].name in pyproject.toml")
    version_match = PROJECT_VERSION_RE.search(body)
    if not version_match:
        raise RuntimeError("Missing [project].version in pyproject.toml")

    name = name_match.group(1).strip()
    version = version_match.group(1).strip()
    if not version:
        raise RuntimeError("Missing [project].version in pyproject.toml")
    return name, version


def read_version(path: Path | None = None) -> str:
    resolved = _resolve_pyproject_path(path)
    name, version = _parse_project_name_and_version(_load_pyproject_text(resolved))
    if name != PROJECT_NAME:
        raise RuntimeError(
            f"Expected [project].name to be {PROJECT_NAME!r} in {resolved}, got {name!r}"
        )
    return version


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
    return result.stdout


def _read_version_from_text(text: str) -> str:
    name, version = _parse_project_name_and_version(text)
    if name != PROJECT_NAME:
        raise RuntimeError(
            f"Expected [project].name to be {PROJECT_NAME!r} in pyproject.toml text, got {name!r}"
        )
    return version


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise RuntimeError("Version auto-bump requires dotted numeric versions like '1.4.0'")
    major = int(parts[0])
    minor = int(parts[1])
    patch = int(parts[2])
    return major, minor, patch


def bump_patch(version: str) -> str:
    major, minor, patch = _parse_version(version)
    return f"{major}.{minor}.{patch + 1}"


def _has_working_tree_changes() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return bool(result.stdout.strip())


def _replace_version_in_text(text: str, version: str) -> str:
    project_match = PROJECT_SECTION_RE.search(text)
    if not project_match:
        raise RuntimeError("Could not find [project] section in pyproject.toml")

    body = project_match.group("body")
    version_match = VERSION_LINE_RE.search(body)
    if not version_match:
        raise RuntimeError("Could not find [project].version entry in pyproject.toml")

    updated_body = (
        body[: version_match.start()]
        + f"{version_match.group('prefix')}{version}{version_match.group('suffix')}"
        + body[version_match.end() :]
    )
    return text[: project_match.start("body")] + updated_body + text[project_match.end("body") :]


def write_version(version: str, path: Path | None = None) -> None:
    resolved = _resolve_pyproject_path(path)
    current_text = resolved.read_text(encoding="utf-8")
    updated_text = _replace_version_in_text(current_text, version)
    if updated_text == current_text:
        return
    resolved.write_text(updated_text, encoding="utf-8", newline="\n")


def resolve_bump_target() -> str:
    current_version = read_version()
    if not _has_working_tree_changes():
        return current_version
    head_text = _read_head_file("pyproject.toml")
    if not head_text:
        return current_version

    head_version = _read_version_from_text(head_text)
    if current_version != head_version:
        return current_version
    return bump_patch(current_version)


def bump_if_needed() -> int:
    current_version = read_version()
    target_version = resolve_bump_target()
    if current_version == target_version:
        return 0
    write_version(target_version)
    print(f"Updated pyproject.toml version to {target_version}")

    # Synchronize uv.lock
    try:
        subprocess.run(["uv", "lock"], check=True, capture_output=True)
        print("Updated uv.lock")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: Failed to update uv.lock: {e}", file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read or bump the project version.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("read", help="Print the current project version.")
    subparsers.add_parser(
        "bump-if-needed",
        help="Bump the patch version when pyproject.toml still matches HEAD.",
    )
    args = parser.parse_args(argv)

    if args.command == "read":
        print(read_version())
        return 0
    if args.command == "bump-if-needed":
        return bump_if_needed()
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
