#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
STAGING_ROOT="$REPO_ROOT/installers/linux/build/apricorn-usb-toolkit"
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

version=$(python3 "$REPO_ROOT/utils/project_version.py" read)
deb_version=${version//+/-}
binary_path=$(find_binary)

rm -rf "$STAGING_ROOT"
mkdir -p "$STAGING_ROOT/DEBIAN"
mkdir -p "$STAGING_ROOT/usr/local/lib/apricorn-usb-toolkit"
mkdir -p "$STAGING_ROOT/usr/share/doc/usb-tool"

install -m 755 "$binary_path" "$STAGING_ROOT/usr/local/lib/apricorn-usb-toolkit/usb"
install -m 644 "$REPO_ROOT/README.md" "$STAGING_ROOT/usr/share/doc/usb-tool/README.md"

sed "s/@DEB_VERSION@/$deb_version/g" "$DEBIAN_TEMPLATE/control" > "$STAGING_ROOT/DEBIAN/control"
cp "$DEBIAN_TEMPLATE/postinst" "$STAGING_ROOT/DEBIAN/postinst"
cp "$DEBIAN_TEMPLATE/postrm" "$STAGING_ROOT/DEBIAN/postrm"
cp "$DEBIAN_TEMPLATE/prerm" "$STAGING_ROOT/DEBIAN/prerm"
cp "$DEBIAN_TEMPLATE/config" "$STAGING_ROOT/DEBIAN/config"
cp "$DEBIAN_TEMPLATE/templates" "$STAGING_ROOT/DEBIAN/templates"
chmod 755 "$STAGING_ROOT/DEBIAN/config" "$STAGING_ROOT/DEBIAN/postinst" "$STAGING_ROOT/DEBIAN/postrm" "$STAGING_ROOT/DEBIAN/prerm"

dpkg-deb --build "$STAGING_ROOT" "$DIST_DIR/apricorn-usb-toolkit-$deb_version-amd64.deb"

echo "Created Debian package dist/apricorn-usb-toolkit-$deb_version-amd64.deb"
