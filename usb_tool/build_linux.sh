#!/bin/bash
# Script to build the Linux executable for the USB tool.

# Ensure the script is run from the project root directory
if [ ! -f "usb.spec" ]; then
    echo "Please run this script from the root of the usb-tool project."
    exit 1
fi

echo "Creating a Linux-specific spec file..."
cp usb.spec usb.spec.linux

echo "Setting up PyInstaller for Linux build..."
# This command will generate the executable in the 'dist' directory.
pyinstaller --clean usb.spec.linux

# Check if the build was successful
if [ $? -eq 0 ]; then
    echo "Build successful! The executable can be found in the 'dist' directory."
else
    echo "Build failed. Please check the output for errors."
    exit 1
fi
