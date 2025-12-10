# usb-tool (Apricorn USB Utility)

Cross-platform CLI and Python library for enumerating Apricorn USB devices and performing a safe READ(10) diagnostic poke.

- Windows, Linux: enumeration + optional poke (requires Admin/root)
- macOS: enumeration only (poke planned)

## Download (standalone builds)

Prebuilt, single-file binaries are published on GitHub Releases; Python is not required.

1) Download the latest asset for your OS:
   - `usb-windows.zip`: unzip and run `usb.exe`.
   - `usb-linux.tar.gz`: extract, `chmod +x usb` if needed, then run `./usb`.
   - `usb-macos.tar.gz`: extract, `chmod +x usb` if needed, then run `./usb` (enumeration only).
2) Run `usb` from a terminal with the commands below. Poke still requires Administrator on Windows and sudo/root on Linux.
3) To update standalone builds, download the newest release asset (standalone binaries do not use `usb-update`).

## Install via pip

Recommended with Python 3.10+.

1) Optional: create a virtual environment
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

2) Install
```bash
pip install .
```

For development:
```bash
pip install -e .[dev]
pre-commit install
```

## Usage

List Apricorn devices (VID 0984):
```bash
usb
```

Safe diagnostic poke (READ(10)):
- Windows: run in an Administrator shell, target by index or `all`
```bash
usb -p 1
usb -p 1,3
usb -p all
```

- Linux: run with sudo, target by index, by path, or `all`
```bash
sudo usb -p 1
sudo usb -p /dev/sdb
sudo usb -p all
```

## Output Fields
The CLI prints normalized device fields. Typical keys include:
- bcdUSB: USB spec version (e.g., 2.0, 3.0)
- idVendor, idProduct: vendor/product IDs (lowercase hex)
- bcdDevice: device revision (4-hex digits)
- iManufacturer, iProduct, iSerial: strings/indices resolved to printable values
- SCSIDevice: whether UAS/SCSI is in use
- driveSizeGB: normalized capacity or `N/A (OOB Mode)`
- usbController: Windows only (e.g., Intel, ASMedia)
- platform-specific identifiers: Windows physical drive number, Linux block path

Version details (best-effort, safely parsed from a vendor READ BUFFER):
- scbPartNumber, hardwareVersion, modelID, mcuFW

Visibility rules:
- The tool always hides bridgeFW from user output (collected internally for gating).
- If bridgeFW does not match bcdDevice (after normalization), the following fields are omitted from output: scbPartNumber, hardwareVersion, modelID, mcuFW.
- Devices reporting no size (OOB Mode) are automatically skipped for poke.

## Platform Notes

Windows
- Enumeration works as standard user; poke requires Administrator.
- Requires PowerShell in PATH. libusb and pywin32 are pinned and installed via markers.

Linux
- Full detail may require root. Helpful tools: `lsusb`, `lshw`, `lsblk`.
- Optional helpers: run `./update_sudoersd.sh` to allow passwordless reads for `lshw`/`fdisk -l` (review before using).

macOS
- Enumeration uses `system_profiler` + `ioreg`. Poke is not yet enabled.
- For tests and some tools: `brew install lsusb`.

## Python API

A per-OS `find_apricorn_device()` is exported from `usb_tool` for convenience:
```python
from usb_tool import find_apricorn_device

devices = find_apricorn_device() or []
for d in devices:
    print(d.iProduct, d.iSerial, d.driveSizeGB)
```
The returned objects are dataclasses:
- Windows: `WinUsbDeviceInfo`
- Linux: `LinuxUsbDeviceInfo`
- macOS: `macOSUsbDeviceInfo`

Field sets are similar across OSes; some fields are platform-specific (e.g., `usbController` on Windows, `blockDevice` on Linux). Output filtering described above applies only to CLI printing; collected fields remain attached to the objects.

## Contributing / Dev
- Code style: black + ruff via pre-commit.
- Tests: `pytest -q`.
- Python 3.10+.
