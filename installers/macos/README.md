# macOS Installer

Builds a signed-or-unsigned `.pkg` that installs `usb` into `/usr/local/lib/usb-tool` and exposes it via `/usr/local/bin/usb` (symlink) for both Intel and Apple Silicon hosts.

## Prerequisites

- macOS 12+
- Xcode command-line tools (provides `pkgbuild`, `productbuild`, and `lipo`)
- Python 3.10+

## Build Instructions

1. Produce PyInstaller binaries for both architectures (run on each host, or provide paths):
   ```bash
   ./build/build_mac.sh   # emits dist/usb on the current architecture
   ```
   Copy the resulting files aside as `dist/usb-macos-arm64` / `dist/usb-macos-x86_64` if you build on two machines.
2. From a macOS machine with both binaries available, run:
   ```bash
   ./build/build_macos_pkg.sh --arm64 dist/usb-macos-arm64 --x86_64 dist/usb-macos-x86_64
   ```
   The script combines them with `lipo` to create a universal binary, stages the payload, and runs `pkgbuild`.
3. The final `usb-tool-<version>-macos.pkg` artifact is placed in `dist/` ready for notarization or distribution.

If only one architecture binary is supplied, the script still builds a pkg using that binary and warns that it is not universal.

Uninstall manually by removing `/usr/local/lib/usb-tool` and the `/usr/local/bin/usb` symlink.
