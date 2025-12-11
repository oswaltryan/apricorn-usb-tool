"""Utility script for turning a PNG source asset into a macOS .icns file.

The script mirrors build/create_ico.py but emits the Apple-specific iconset
folder layout and (optionally) shells out to `iconutil` when available.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image

ICONSET_SPECS: tuple[tuple[int, int], ...] = (
    (16, 1),
    (16, 2),
    (32, 1),
    (32, 2),
    (128, 1),
    (128, 2),
    (256, 1),
    (256, 2),
    (512, 1),
    (512, 2),
)


def _resample_filter() -> int:
    resampling_cls = getattr(Image, "Resampling", None)
    if resampling_cls is not None:
        return int(resampling_cls.LANCZOS)
    return int(getattr(Image, "LANCZOS"))


def _target_filename(base: int, scale: int) -> str:
    suffix = "" if scale == 1 else "@2x"
    return f"icon_{base}x{base}{suffix}.png"


def _ensure_iconset_dir(iconset_dir: Path) -> None:
    iconset_dir.mkdir(parents=True, exist_ok=True)


def build_iconset(png_path: Path, iconset_dir: Path) -> None:
    print(f"[INFO] Building iconset from {png_path}")
    with Image.open(png_path) as img:
        source = img.convert("RGBA")
        resample = _resample_filter()
        _ensure_iconset_dir(iconset_dir)

        for base, scale in ICONSET_SPECS:
            target_size = base * scale
            filename = _target_filename(base, scale)
            out_path = iconset_dir / filename
            resized = source.resize((target_size, target_size), resample)
            resized.save(out_path)
            print(f"[INFO] Wrote {out_path} ({target_size}px)")


def maybe_run_iconutil(iconset_dir: Path, icns_path: Path, skip: bool) -> None:
    if skip:
        print(f"[INFO] Skipping iconutil invocation. Iconset at: {iconset_dir}")
        return

    iconutil = shutil.which("iconutil")
    if iconutil is None:
        print("[WARN] iconutil not found on PATH; skipping .icns packaging.")
        print(
            f"       Run on macOS with: iconutil -c icns {iconset_dir} -o {icns_path}"
        )
        return

    cmd = [iconutil, "-c", "icns", str(iconset_dir), "-o", str(icns_path)]
    print(f"[INFO] Running {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"[SUCCESS] Created {icns_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a macOS .icns file from a source PNG."
    )
    parser.add_argument("png", type=Path, help="High-resolution source PNG")
    parser.add_argument(
        "--iconset-dir",
        type=Path,
        default=None,
        help="Destination .iconset directory (defaults to <PNG>.iconset)",
    )
    parser.add_argument(
        "--icns",
        type=Path,
        default=None,
        help="Optional output .icns file path (defaults to <PNG>.icns)",
    )
    parser.add_argument(
        "--skip-iconutil",
        action="store_true",
        help="Do not call iconutil automatically (useful on non-macOS hosts).",
    )
    args = parser.parse_args()

    png_path = args.png.resolve()
    if not png_path.is_file():
        raise FileNotFoundError(png_path)

    iconset_dir = (
        args.iconset_dir
        if args.iconset_dir is not None
        else png_path.with_suffix(".iconset")
    )
    icns_path = args.icns if args.icns is not None else png_path.with_suffix(".icns")

    build_iconset(png_path, iconset_dir)
    maybe_run_iconutil(iconset_dir, icns_path, skip=args.skip_iconutil)


if __name__ == "__main__":
    main()
