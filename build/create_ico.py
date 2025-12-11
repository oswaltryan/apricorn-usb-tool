import os
import sys

from PIL import Image

def png_to_ico(png_path: str, ico_path: str | None = None):
    print(f"[INFO] Requested PNG → ICO")
    print(f"[INFO] PNG path: {png_path!r}")
    print(f"[INFO] Current working dir: {os.getcwd()}")

    if not os.path.isfile(png_path):
        print(f"[ERROR] File not found: {png_path}")
        print("[DEBUG] Files in current directory:")
        for name in os.listdir():
            print("   -", name)
        return

    if ico_path is None:
        base, _ = os.path.splitext(png_path)
        ico_path = base + ".ico"

    try:
        img = Image.open(png_path)
        print(f"[INFO] Opened image: {img.size} pixels, mode={img.mode}")

        # Convert to RGBA if needed (icons like RGBA)
        if img.mode not in ("RGBA", "RGB"):
            print(f"[INFO] Converting image mode from {img.mode} to RGBA")
            img = img.convert("RGBA")

        sizes = [(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
        print(f"[INFO] Saving ICO to: {ico_path!r} with sizes: {sizes}")
        img.save(ico_path, sizes=sizes)

        print("[SUCCESS] ICO file created.")
        print(f"[SUCCESS] Output file: {os.path.abspath(ico_path)}")
    except Exception as e:
        print("[ERROR] Exception while converting image:")
        print(repr(e))


if __name__ == "__main__":
    # Allow: python convert_icon.py myicon.png myicon.ico
    # or:    python convert_icon.py myicon.png
    if len(sys.argv) < 2:
        print("Usage: python convert_icon.py <input.png> [output.ico]")
    else:
        png = sys.argv[1]
        ico = sys.argv[2] if len(sys.argv) > 2 else None
        png_to_ico(png, ico)

    # Keep window open if double-clicked
    if sys.stdin.isatty() is False:  # crude check, but helps when double-clicking
        input("Press Enter to exit...")
