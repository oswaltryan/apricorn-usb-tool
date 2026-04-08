#!/bin/sh
set -eu

DEFAULT_INSTALL_DIR="/usr/local/lib/apricorn-usb-toolkit"
LEGACY_INSTALL_DIR="/usr/local/lib/usb-tool"
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
LINK="/usr/local/bin/usb"

if [ "$(id -u)" != "0" ]; then
    echo "This uninstaller must be run as root." >&2
    exit 1
fi

if [ -L "$LINK" ]; then
    TARGET=$(readlink "$LINK" 2>/dev/null || true)
    case "$TARGET" in
        *apricorn-usb-toolkit/usb|\
        *usb-tool/usb)
            rm -f "$LINK"
            ;;
    esac
elif [ -f "$LINK" ] && [ -x "$LINK" ]; then
    echo "$LINK exists and is not managed by Apricorn USB Toolkit; skipping" >&2
fi

if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "Removed $INSTALL_DIR"
else
    echo "$INSTALL_DIR not found; nothing to remove."
fi

if [ "$INSTALL_DIR" = "$DEFAULT_INSTALL_DIR" ] && [ -d "$LEGACY_INSTALL_DIR" ]; then
    rm -rf "$LEGACY_INSTALL_DIR"
    echo "Removed legacy install dir $LEGACY_INSTALL_DIR"
fi

echo "Apricorn USB Toolkit CLI removed."
