# Linux Installer

This directory contains the files needed to build a `.deb` installer for Debian-based Linux distributions.

## Prerequisites

- Debian-based Linux distribution
- `dpkg-deb`

## Build Instructions

1.  Build the `usb` executable by running `build/build_linux.sh` from the root of the project.
2.  Run `dpkg-deb --build installers/linux/usb-tool` to build the installer.
