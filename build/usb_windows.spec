# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import sys

block_cipher = None

SPEC_DIR = os.path.abspath(os.path.dirname(sys.argv[0])) if sys.argv else os.path.abspath(".")
ICON_PATH = os.path.join(SPEC_DIR, "USBTool.ico")
SITE_PACKAGES = os.path.abspath(os.path.join(SPEC_DIR, "..", ".venv_build", "Lib", "site-packages"))


def _dist_info_dir(dist_name: str) -> str:
    matches = glob.glob(os.path.join(SITE_PACKAGES, f"{dist_name}-*.dist-info"))
    if not matches:
        raise FileNotFoundError(f"dist-info for {dist_name} not found in {SITE_PACKAGES}")
    return matches[0]

a = Analysis(
    ['..\\usb_tool\\cross_usb.py'],
    pathex=[],
    binaries=[],
    datas=[
        (_dist_info_dir("pkg_about"), os.path.basename(_dist_info_dir("pkg_about"))),
        (_dist_info_dir("libusb"), os.path.basename(_dist_info_dir("libusb"))),
        (_dist_info_dir("py_utlx"), os.path.basename(_dist_info_dir("py_utlx"))),
        (
            os.path.join(
                SITE_PACKAGES, "libusb", "_platform", "windows", "x86_64", "libusb-1.0.dll"
            ),
            "libusb\\_platform\\windows\\x86_64",
        ),
        ('..\\usb_tool\\_cached_version.txt', 'usb_tool'),
    ],
    hiddenimports=['winreg', 'libusb', 'pkg_about', 'ctypes', 'win32com'],
    hookspath=['build/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='usb-windows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)
