# Linux Installer

Two options exist for distributing the standalone Apricorn USB Toolkit Linux binary.

## Debian Package (.deb)

1. Build the PyInstaller binary (or let the helper do it):
   ```bash
   ./build/build_linux_installer.sh
   ```
   The script runs `build_linux.sh` (unless `SKIP_PYINSTALLER=1`), stages the payload, and creates `dist/apricorn-usb-toolkit-<version>-amd64.deb` using the templates under `installers/linux/debian/`.
   Linux release artifacts are expected to target a `glibc` 2.31 floor. Build them on an Ubuntu 20.04 or equivalent baseline; building on newer distros can bundle a newer `libpython` and fail at runtime with `GLIBC_2.xx not found`.
2. Install via apt:
   ```bash
   sudo apt install ./dist/apricorn-usb-toolkit-<version>-amd64.deb
   ```
3. Uninstall:
   ```bash
   sudo apt remove usb-tool
   ```

## Manual Install Script

If you cannot use a `.deb`, copy the binary into place with the helper:

```bash
sudo bash installers/linux/install.sh --binary dist/usb-linux
```

This copies the binary to `/usr/local/lib/apricorn-usb-toolkit/usb` and symlinks `/usr/local/bin/usb`.

To uninstall a manual install:

```bash
sudo bash installers/linux/uninstall.sh
```

Both flows require root privileges to manipulate `/usr/local` and the PATH symlink.
