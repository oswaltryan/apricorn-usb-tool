#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
STAGING_ROOT="$REPO_ROOT/installers/linux/build/usb-tool"
DEBIAN_TEMPLATE="$REPO_ROOT/installers/linux/debian/DEBIAN"

mkdir -p "$DIST_DIR"

if [[ "${SKIP_PYINSTALLER:-0}" != "1" ]]; then
    "$REPO_ROOT/build/build_linux.sh"
fi

find_binary() {
    local candidates=(
        "$DIST_DIR/usb-linux"
        "$DIST_DIR/usb"
        "$DIST_DIR/usb/usb"
    )
    for candidate in "${candidates[@]}"; do
        if [[ -f "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done
    echo "Unable to locate PyInstaller binary in $DIST_DIR" >&2
    exit 1
}

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
deb_version=${version//+/-}
binary_path=$(find_binary)

rm -rf "$STAGING_ROOT"
mkdir -p "$STAGING_ROOT/DEBIAN"
mkdir -p "$STAGING_ROOT/usr/local/lib/usb-tool"
mkdir -p "$STAGING_ROOT/usr/share/doc/usb-tool"

install -m 755 "$binary_path" "$STAGING_ROOT/usr/local/lib/usb-tool/usb"
install -m 644 "$REPO_ROOT/README.md" "$STAGING_ROOT/usr/share/doc/usb-tool/README.md"

sed "s/@DEB_VERSION@/$deb_version/g" "$DEBIAN_TEMPLATE/control" > "$STAGING_ROOT/DEBIAN/control"
cp "$DEBIAN_TEMPLATE/postinst" "$STAGING_ROOT/DEBIAN/postinst"
cp "$DEBIAN_TEMPLATE/prerm" "$STAGING_ROOT/DEBIAN/prerm"
chmod 755 "$STAGING_ROOT/DEBIAN/postinst" "$STAGING_ROOT/DEBIAN/prerm"

dpkg-deb --build "$STAGING_ROOT" "$DIST_DIR/usb-tool-$deb_version-amd64.deb"

echo "Created Debian package dist/usb-tool-$deb_version-amd64.deb"
