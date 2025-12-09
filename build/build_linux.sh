#!/bin/bash
set -e

VENV_PATH=".venv_build"
SPEC_FILE="build/usb_linux.spec"

# Create a virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    python3 -m venv $VENV_PATH
fi

echo "Activating virtual environment..."
source $VENV_PATH/bin/activate

# Install dependencies
echo "Installing dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install wheel
python3 -m pip install .
python3 -m pip install pyinstaller pkg_about

# Run PyInstaller
echo "Running PyInstaller..."
pyinstaller --clean --noconfirm $SPEC_FILE

echo "Build complete. The single-file executable is in the 'dist' folder."
