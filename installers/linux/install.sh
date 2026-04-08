#!/bin/sh
set -eu

show_usage() {
    cat <<'USAGE'
Usage: ./installers/linux/install.sh [--binary <path>] [--prefix <dir>]

Copies the standalone Apricorn USB Toolkit binary into /usr/local/lib/apricorn-usb-toolkit and
symlinks /usr/local/bin/usb so the CLI is available on PATH.

Options:
  --binary PATH   Path to the PyInstaller binary (default: dist/usb-linux)
  --prefix DIR    Installation directory (default: /usr/local/lib/apricorn-usb-toolkit)
  -h, --help      Show this message
USAGE
}

BINARY="dist/usb-linux"
DEFAULT_PREFIX="/usr/local/lib/apricorn-usb-toolkit"
LEGACY_PREFIX="/usr/local/lib/usb-tool"
PREFIX="$DEFAULT_PREFIX"
LINK="/usr/local/bin/usb"

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

if [ "$PREFIX" = "$DEFAULT_PREFIX" ] && [ -d "$LEGACY_PREFIX" ]; then
    if [ -f "$LEGACY_PREFIX/usb" ] && [ ! -f "$PREFIX/usb" ]; then
        mv "$LEGACY_PREFIX/usb" "$PREFIX/usb" 2>/dev/null || true
    fi
    rm -f "$LEGACY_PREFIX/usb"
    rmdir "$LEGACY_PREFIX" 2>/dev/null || true
fi

install -m 755 "$BINARY" "$PREFIX/usb"
ln -sf "$PREFIX/usb" "$LINK"

echo "Apricorn USB Toolkit installed to $PREFIX. Invoke 'usb' from any shell."
