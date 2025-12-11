from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image

BUILD_DIR = Path(__file__).resolve().parent.parent


def png_to_ico(
    png_path: str | os.PathLike[str], ico_path: str | os.PathLike[str] | None = None
) -> None:
    print("[INFO] Requested PNG -> ICO")
    print(f"[INFO] PNG path: {png_path!r}")
    print(f"[INFO] Current working dir: {os.getcwd()}")

    source_png = Path(png_path)

    if not source_png.is_file():
        print(f"[ERROR] File not found: {source_png}")
        print("[DEBUG] Files in current directory:")
        for name in os.listdir():
            print("   -", name)
        return

    if ico_path is None:
        target_path = BUILD_DIR / f"{source_png.stem}.ico"
    else:
        target_path = Path(ico_path)

    try:
        img = Image.open(source_png)
        print(f"[INFO] Opened image: {img.size} pixels, mode={img.mode}")

        # Convert to RGBA if needed (icons like RGBA)
        if img.mode not in ("RGBA", "RGB"):
            print(f"[INFO] Converting image mode from {img.mode} to RGBA")
            img = img.convert("RGBA")

        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        print(f"[INFO] Saving ICO to: {target_path!r} with sizes: {sizes}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(target_path, sizes=sizes)

        print("[SUCCESS] ICO file created.")
        print(f"[SUCCESS] Output file: {target_path.resolve()}")
    except Exception as e:
        print("[ERROR] Exception while converting image:")
        print(repr(e))


if __name__ == "__main__":
    # Allow: python create_ico.py myicon.png myicon.ico
    # or:    python create_ico.py myicon.png
    if len(sys.argv) < 2:
        print("Usage: python create_ico.py <input.png> [output.ico]")
    else:
        png = sys.argv[1]
        ico = sys.argv[2] if len(sys.argv) > 2 else None
        png_to_ico(png, ico)

    # Keep window open if double-clicked
    if sys.stdin.isatty() is False:  # crude check, but helps when double-clicking
        input("Press Enter to exit...")
