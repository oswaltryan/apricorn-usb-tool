# macOS Installer

This directory contains the files needed to build a `.pkg` installer for macOS.

## Prerequisites

- macOS
- `packagesbuild`

## Build Instructions

1.  Build the `usb` executable by running `build/build_mac.sh` from the root of the project.
2.  Run `packagesbuild installers/macos/usb-tool.pkgproj` to build the installer.
