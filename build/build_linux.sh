#!/bin/bash
set -e

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install .
pip install pyinstaller

# Run PyInstaller

# Dynamically create the spec file with the absolute path
PROJECT_ROOT=$(pwd)
TEMP_SPEC_FILE="build/temp_usb_linux.spec"

cat <<EOF > "${TEMP_SPEC_FILE}"
# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['${PROJECT_ROOT}/usb_tool/cross_usb.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['libusb'],
    hookspath=[],
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
    [],
    exclude_binaries=True,
    name='usb',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='usb',
)
EOF

# Run PyInstaller with the temporary spec file
pyinstaller "${TEMP_SPEC_FILE}"

# Clean up temporary spec file
rm "${TEMP_SPEC_FILE}"
