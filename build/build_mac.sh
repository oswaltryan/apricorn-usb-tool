#!/bin/bash
set -e

# Navigate to the project root directory
SCRIPT_DIR=$(dirname "$0")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_ROOT"

# Create a virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install dependencies
# Check if requirements.txt exists and install from it
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "No requirements.txt found. Assuming minimal dependencies."
fi
pip install pyinstaller # Ensure pyinstaller is installed in the venv

# Run PyInstaller from the project root, referencing the spec file correctly
pyinstaller "$SCRIPT_DIR"/usb_mac.spec --distpath "$SCRIPT_DIR"/dist

# Optional: Deactivate virtual environment
deactivate
