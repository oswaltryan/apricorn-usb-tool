#!/bin/sh
set -eu

show_usage() {
    cat <<'USAGE'
Usage: ./installers/macos/install.sh [--binary <path>] [--prefix <dir>] [--install-nopasswd-sudo]

Copies the standalone macOS usb binary into /usr/local/lib/usb-tool and
symlinks /usr/local/bin/usb so the CLI is available on PATH.

Options:
  --binary PATH              Path to the standalone binary (default: dist/usb-macos)
  --prefix DIR               Installation directory (default: /usr/local/lib/usb-tool)
  --install-nopasswd-sudo    Install an opt-in /etc/sudoers.d rule for /usr/local/bin/usb
  -h, --help                 Show this message
USAGE
}

BINARY="dist/usb-macos"
PREFIX="/usr/local/lib/usb-tool"
LINK="/usr/local/bin/usb"
HELPER_NAME="update_sudoersd_macos.sh"
INSTALL_NOPASSWD_SUDO=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --binary)
            shift
            [ -n "${1-}" ] || { echo "Missing value for --binary" >&2; exit 1; }
            BINARY="$1"
            ;;
        --prefix)
            shift
            [ -n "${1-}" ] || { echo "Missing value for --prefix" >&2; exit 1; }
            PREFIX="$1"
            ;;
        --install-nopasswd-sudo)
            INSTALL_NOPASSWD_SUDO=1
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
    echo "This installer must be run as root." >&2
    exit 1
fi

if [ ! -f "$BINARY" ]; then
    echo "Binary not found: $BINARY" >&2
    exit 1
fi

install -d -m 755 "$PREFIX"
install -m 755 "$BINARY" "$PREFIX/usb"
install -m 755 "$(cd "$(dirname "$0")/../.." && pwd)/$HELPER_NAME" "$PREFIX/$HELPER_NAME"
ln -sf "$PREFIX/usb" "$LINK"

if [ "$INSTALL_NOPASSWD_SUDO" -eq 1 ]; then
    "$PREFIX/$HELPER_NAME" --command "$LINK"
fi

echo "usb-tool installed to $PREFIX. Invoke 'usb' from any shell."
if [ "$INSTALL_NOPASSWD_SUDO" -eq 0 ]; then
    echo "To allow noninteractive 'sudo -n usb', run: sudo $PREFIX/$HELPER_NAME"
fi
