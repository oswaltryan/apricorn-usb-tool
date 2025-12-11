# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

SPEC_DIR = os.path.abspath(os.path.dirname(sys.argv[0])) if sys.argv else os.path.abspath(".")
ICON_PATH = os.path.join(SPEC_DIR, "USBTool.ico")

a = Analysis(
    ['..\\usb_tool\\cross_usb.py'],
    pathex=[],
    binaries=[],
    datas=[('..\\.venv_build\\Lib\\site-packages\\pkg_about-2.0.9.dist-info',
            'pkg_about-2.0.9.dist-info'),
           ('..\\.venv_build\\Lib\\site-packages\\libusb-1.0.29.post1.dist-info',
            'libusb-1.0.29.post1.dist-info'),
           ('..\\.venv_build\\Lib\\site-packages\\py_utlx-2.0.1.dist-info',
            'py_utlx-2.0.1.dist-info'),
           ('..\\.venv_build\\Lib\\site-packages\\libusb\\_platform\\windows\\x86_64\\libusb-1.0.dll',
            'libusb\\_platform\\windows\\x86_64'),
           ('..\\usb_tool\\_cached_version.txt', 'usb_tool')],
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
    name='usb',
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
