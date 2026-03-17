#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$REPO_ROOT/.venv_build"
SPEC_FILE="$REPO_ROOT/build/usb_linux.spec"
MAX_GLIBC="${USB_TOOL_MAX_GLIBC:-2.31}"

cd "$REPO_ROOT"

# Create a virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Install dependencies
echo "Installing dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install wheel
python3 -m pip install .
python3 -m pip install pyinstaller pkg_about

# Ensure the bundled interpreter stays compatible with the advertised Debian floor.
echo "Validating Python shared library glibc floor..."
python3 "$REPO_ROOT/build/check_glibc_floor.py" --max-glibc "$MAX_GLIBC" --label "PyInstaller Python shared library"

# Run PyInstaller
echo "Running PyInstaller..."
pyinstaller --clean --noconfirm "$SPEC_FILE"

echo "Build complete. The single-file executable is in the 'dist' folder."
