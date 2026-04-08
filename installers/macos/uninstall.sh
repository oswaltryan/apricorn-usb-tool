#!/bin/sh
set -eu

DEFAULT_INSTALL_DIR="/usr/local/lib/apricorn-usb-toolkit"
LEGACY_INSTALL_DIR="/usr/local/lib/usb-tool"
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
LINK="/usr/local/bin/usb"
HELPER="$INSTALL_DIR/update_sudoersd_macos.sh"
LEGACY_HELPER="$LEGACY_INSTALL_DIR/update_sudoersd_macos.sh"
REMOVE_NOPASSWD_SUDO=0

verify_uninstall() {
    FAILED=0

    echo
    echo "Verification:"

    if [ -e "$LINK" ] || [ -L "$LINK" ]; then
        echo "  FAIL: $LINK still exists"
        FAILED=1
    else
        echo "  OK: $LINK is absent"
    fi

    if [ -d "$INSTALL_DIR" ]; then
        echo "  FAIL: $INSTALL_DIR still exists"
        FAILED=1
    else
        echo "  OK: $INSTALL_DIR is absent"
    fi

    if [ "$INSTALL_DIR" = "$DEFAULT_INSTALL_DIR" ] && [ -d "$LEGACY_INSTALL_DIR" ]; then
        echo "  FAIL: $LEGACY_INSTALL_DIR still exists"
        FAILED=1
    elif [ "$INSTALL_DIR" = "$DEFAULT_INSTALL_DIR" ]; then
        echo "  OK: $LEGACY_INSTALL_DIR is absent"
    fi

    if command -v usb >/dev/null 2>&1; then
        echo "  FAIL: 'usb' still resolves to $(command -v usb)"
        FAILED=1
    else
        echo "  OK: 'usb' is no longer on PATH"
    fi

    if [ "$FAILED" -ne 0 ]; then
        echo
        echo "Uninstall verification failed."
        exit 1
    fi

    echo
    echo "Uninstall verification passed."
}

show_usage() {
    cat <<'USAGE'
Usage: ./installers/macos/uninstall.sh [--remove-nopasswd-sudo]

Removes the manually installed Apricorn USB Toolkit macOS binary and PATH symlink.

Options:
  --remove-nopasswd-sudo  Also remove /etc/sudoers.d/usb-tool-nopasswd
  -h, --help              Show this message
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --remove-nopasswd-sudo)
            REMOVE_NOPASSWD_SUDO=1
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_usage
            exit 1
            ;;
    esac
    shift
done

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

if [ "$REMOVE_NOPASSWD_SUDO" -eq 1 ]; then
    if [ -x "$HELPER" ]; then
        "$HELPER" --remove
    elif [ -x "$LEGACY_HELPER" ]; then
        "$LEGACY_HELPER" --remove
    else
        rm -f /etc/sudoers.d/usb-tool-nopasswd
    fi
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
verify_uninstall
