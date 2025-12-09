#!/bin/bash
set -e

VENV_DIR="build/.venv"
SPEC_FILE="build/usb_mac.spec"

# Create a virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv $VENV_DIR
fi

echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Install dependencies
echo "Installing dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -e .
python3 -m pip install pyinstaller

# Run PyInstaller
echo "Running PyInstaller..."
pyinstaller --clean -y $SPEC_FILE

echo "Build complete. The executable is in the 'dist' folder."