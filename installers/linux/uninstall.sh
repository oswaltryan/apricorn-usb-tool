#!/bin/sh
set -eu

INSTALL_DIR="${INSTALL_DIR:-/usr/local/lib/usb-tool}"
LINK="/usr/local/bin/usb"

if [ "$(id -u)" != "0" ]; then
    echo "This uninstaller must be run as root." >&2
    exit 1
fi

if [ -L "$LINK" ]; then
    TARGET=$(readlink "$LINK" 2>/dev/null || true)
    case "$TARGET" in
        *usb-tool/usb)
            rm -f "$LINK"
            ;;
    esac
elif [ -f "$LINK" ] && [ -x "$LINK" ]; then
    echo "$LINK exists and is not managed by usb-tool; skipping" >&2
fi

if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "Removed $INSTALL_DIR"
else
    echo "$INSTALL_DIR not found; nothing to remove."
fi

echo "usb-tool CLI removed."
