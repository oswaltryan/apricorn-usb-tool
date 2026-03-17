#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import sysconfig
from pathlib import Path

GLIBC_VERSION_RE = re.compile(r"GLIBC_([0-9]+(?:\.[0-9]+)*)")


def parse_glibc_versions(text: str) -> list[tuple[int, ...]]:
    versions = {
        tuple(int(part) for part in match.group(1).split("."))
        for match in GLIBC_VERSION_RE.finditer(text)
    }
    return sorted(versions)


def parse_version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def format_version(version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)


def max_glibc_version(text: str) -> tuple[int, ...] | None:
    versions = parse_glibc_versions(text)
    return versions[-1] if versions else None


def current_python_shared_library() -> Path:
    base_prefix = Path(sys.base_prefix)
    libdir = sysconfig.get_config_var("LIBDIR")
    instsoname = sysconfig.get_config_var("INSTSONAME")
    ldlibrary = sysconfig.get_config_var("LDLIBRARY")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"

    search_roots = []
    for candidate in [libdir, base_prefix / "lib", base_prefix / "lib64"]:
        if not candidate:
            continue
        path = Path(candidate)
        if path not in search_roots:
            search_roots.append(path)

    candidate_names = [
        name for name in [instsoname, ldlibrary, f"libpython{version}.so.1.0"] if name
    ]
    for root in search_roots:
        for name in candidate_names:
            candidate = root / name
            if candidate.is_file():
                return candidate.resolve()

    for root in search_roots:
        if not root.is_dir():
            continue
        matches = sorted(root.glob(f"libpython{version}.so*"))
        if matches:
            return matches[0].resolve()

    raise FileNotFoundError(
        "Unable to locate the current Python shared library. "
        "Set --elf explicitly if the interpreter layout is unusual."
    )


def read_symbol_versions(elf_path: Path) -> str:
    commands = [
        ["objdump", "-T", str(elf_path)],
        ["readelf", "--version-info", str(elf_path)],
    ]
    failures: list[str] = []

    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            failures.append(f"{command[0]} not found")
            continue
        except subprocess.CalledProcessError as exc:
            failures.append(exc.stderr.strip() or exc.stdout.strip() or str(exc))
            continue
        return result.stdout

    raise RuntimeError("Unable to inspect ELF symbol versions: " + "; ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if an ELF depends on a newer GLIBC than the allowed floor."
    )
    parser.add_argument(
        "--elf",
        type=Path,
        help="ELF to inspect. Defaults to the active Python shared library.",
    )
    parser.add_argument(
        "--max-glibc",
        default="2.31",
        help="Maximum allowed GLIBC version requirement.",
    )
    parser.add_argument(
        "--label",
        default="ELF",
        help="Human-readable label for diagnostics.",
    )
    args = parser.parse_args()

    elf_path = args.elf.resolve() if args.elf else current_python_shared_library()
    allowed = parse_version(args.max_glibc)
    symbol_text = read_symbol_versions(elf_path)
    actual = max_glibc_version(symbol_text)

    if actual is None:
        print(
            f"{args.label} does not reference versioned GLIBC symbols: {elf_path}",
            file=sys.stderr,
        )
        return 0

    if actual > allowed:
        print(
            f"{args.label} requires GLIBC_{format_version(actual)}, which exceeds the "
            f"configured floor GLIBC_{format_version(allowed)}: {elf_path}",
            file=sys.stderr,
        )
        return 1

    print(
        f"{args.label} max GLIBC requirement is GLIBC_{format_version(actual)} "
        f"(allowed: GLIBC_{format_version(allowed)}): {elf_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
