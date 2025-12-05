#!/bin/bash
set -e

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install .
pip install pyinstaller

# Run PyInstaller
pyinstaller build/usb_mac.spec
