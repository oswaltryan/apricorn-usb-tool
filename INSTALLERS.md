# Installer Guide

## Windows (.msi)
- Build with `pwsh build/build_windows_msi.ps1` (requires WiX Toolset). The helper runs PyInstaller, then `candle`/`light`, and drops `dist/usb-tool-<version>-x64.msi`.
- Install by double-clicking the MSI or running `msiexec /i usb-tool-<version>-x64.msi`. The package copies `usb.exe` to `%ProgramFiles%\Apricorn\usb-tool` and appends that path to the system `PATH`.
- Uninstall via **Settings → Apps → usb-tool** or `msiexec /x {ProductCode}`. The uninstall removes the binary and PATH entry.

## Linux (.deb + scripts)
- Build with `./build/build_linux_installer.sh` (needs `dpkg-deb`). The script stages the payload, copies docs, applies `installers/linux/debian/DEBIAN/*`, and emits `dist/usb-tool-<version>-amd64.deb`.
- Install via `sudo apt install ./dist/usb-tool-<version>-amd64.deb`. The package installs to `/usr/local/lib/usb-tool` and symlinks `/usr/local/bin/usb`.
- Uninstall via `sudo apt remove usb-tool`.
- Manual path (non-Debian): run `sudo bash installers/linux/install.sh --binary dist/usb-linux` to copy the standalone binary into place. Remove manual installs with `sudo bash installers/linux/uninstall.sh` (deletes `/usr/local/lib/usb-tool` and the `/usr/local/bin/usb` symlink if it points to that directory).

## macOS (.pkg)
- Build with `./build/build_macos_pkg.sh --arm64 <path> --x86_64 <path>` after producing PyInstaller binaries for both architectures. The script combines them with `lipo` (universal) and calls `pkgbuild`, creating `dist/usb-tool-<version>-macos.pkg`.
- Install by double-clicking the PKG or running `sudo installer -pkg dist/usb-tool-<version>-macos.pkg -target /`. The package places the CLI at `/usr/local/lib/usb-tool/usb` and symlinks `/usr/local/bin/usb`. It runs natively on Intel and Apple Silicon Macs (including the Mac mini M4).
- Uninstall manually: remove `/usr/local/lib/usb-tool` and `/usr/local/bin/usb` (if it points to that directory).

## Verification Checklist
- After installing on any OS, open a **new** terminal to ensure PATH updates are applied and run `usb --version` followed by `usb --json` to confirm enumerations run without stack traces.
- Run `usb -p` with a dry target where supported (Windows/Linux) to ensure permissions errors are readable when not elevated.
- Uninstall and verify:
  - Windows: `%ProgramFiles%\Apricorn\usb-tool` folder removed and PATH no longer includes it.
  - Linux: `/usr/local/lib/usb-tool` removed and `/usr/local/bin/usb` absent (or symlink restored to user-managed binary).
  - macOS: same as Linux plus Gatekeeper/quarantine cleared (use `spctl --assess` if signed).
- Re-run the installer to confirm upgrades succeed without manual cleanup.
