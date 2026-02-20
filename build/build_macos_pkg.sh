#!/bin/bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: ./build/build_macos_pkg.sh [--arm64 <path>] [--x86_64 <path>] [--skip-pyinstaller]

Combines the provided binaries (or the default dist/usb-macos build) into a
universal CLI and generates a macOS installer package.
USAGE
}

ARM_BIN=""
X64_BIN=""
SKIP_PYINSTALLER=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arm64)
            shift
            [[ -n "${1:-}" ]] || { echo "Missing value for --arm64" >&2; exit 1; }
            ARM_BIN="$1"
            ;;
        --x86_64)
            shift
            [[ -n "${1:-}" ]] || { echo "Missing value for --x86_64" >&2; exit 1; }
            X64_BIN="$1"
            ;;
        --skip-pyinstaller)
            SKIP_PYINSTALLER=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
    shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
STAGING_ROOT="$REPO_ROOT/installers/macos/build/root"
UNIVERSAL_DIR="$REPO_ROOT/installers/macos/build/universal"
SCRIPTS_DIR="$REPO_ROOT/installers/macos/scripts"

mkdir -p "$DIST_DIR"

if [[ $SKIP_PYINSTALLER -eq 0 ]]; then
    "$REPO_ROOT/build/build_mac.sh"
fi

abs_path() {
    python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())' "$1"
}

find_binary() {
    local candidates=(
        "$DIST_DIR/usb-macos"
        "$DIST_DIR/usb"
        "$DIST_DIR/usb/usb"
    )
    for candidate in "${candidates[@]}"; do
        if [[ -f "$candidate" ]]; then
            abs_path "$candidate"
            return 0
        fi
    done
    echo "Unable to find PyInstaller output under $DIST_DIR" >&2
    exit 1
}

selected_binary=""
if [[ -n "$ARM_BIN" && -n "$X64_BIN" ]]; then
    mkdir -p "$UNIVERSAL_DIR"
    arm_path=$(abs_path "$ARM_BIN")
    x64_path=$(abs_path "$X64_BIN")
    selected_binary="$UNIVERSAL_DIR/usb"
    /usr/bin/lipo -create -output "$selected_binary" "$arm_path" "$x64_path"
    /bin/chmod 755 "$selected_binary"
elif [[ -n "$ARM_BIN" ]]; then
    selected_binary=$(abs_path "$ARM_BIN")
    echo "Warning: only ARM64 binary supplied; resulting pkg will not run on Intel Macs" >&2
elif [[ -n "$X64_BIN" ]]; then
    selected_binary=$(abs_path "$X64_BIN")
    echo "Warning: only x86_64 binary supplied; resulting pkg will not run natively on Apple Silicon" >&2
else
    selected_binary=$(find_binary)
    echo "Using default PyInstaller binary at $selected_binary"
fi

pyproject="$REPO_ROOT/pyproject.toml"
if [[ ! -f "$pyproject" ]]; then
    echo "pyproject.toml not found at $pyproject" >&2
    exit 1
fi
version=$(grep -E '^[[:space:]]*version[[:space:]]*=' "$pyproject" | head -n 1 | sed -E "s/^[[:space:]]*version[[:space:]]*=[[:space:]]*['\\\"]([^'\\\"]+)['\\\"].*/\\1/")
if [[ -z "$version" ]]; then
    echo "Unable to parse version from pyproject.toml" >&2
    exit 1
fi
version_file="$REPO_ROOT/src/usb_tool/_cached_version.txt"
printf "%s\n" "$version" > "$version_file" || true
numeric=${version%%[^0-9.]*}
IFS='.' read -r major minor patch <<<"$numeric"
major=${major:-0}
minor=${minor:-0}
patch=${patch:-0}
pkg_version="$major.$minor.$patch"

rm -rf "$STAGING_ROOT"
mkdir -p "$STAGING_ROOT/usr/local/lib/usb-tool"
install -m 755 "$selected_binary" "$STAGING_ROOT/usr/local/lib/usb-tool/usb"

pkg_path="$DIST_DIR/usb-tool-$version-macos.pkg"
/usr/bin/pkgbuild \
    --root "$STAGING_ROOT" \
    --scripts "$SCRIPTS_DIR" \
    --identifier "com.apricorn.usbtool" \
    --version "$pkg_version" \
    "$pkg_path"

echo "Created macOS installer at $pkg_path"
