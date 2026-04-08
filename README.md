# Apricorn USB Toolkit

Cross-platform CLI and Python library for discovering Apricorn USB devices and performing low-level USB/SCSI operations consistently across Windows, Linux, and macOS.

## Why this exists

Low-level USB and SCSI workflows are fragmented across operating systems. Existing tools are often platform-specific, inconsistent, or poorly suited for repeatable validation and manufacturing workflows. This project was built to provide a unified interface for Apricorn device discovery, inspection, and low-level operations across major desktop platforms.

Instead of stitching together one-off scripts per OS, `apricorn-usb-toolkit` provides a reusable contract with platform backends that normalize hardware identity, transport details, media state, and version metadata into deterministic output for automation and qualification pipelines.

## Architecture

```mermaid
flowchart LR
  User["Operator / Validation Automation"] --> CLI["usb CLI (src/usb_tool/cli.py)"]
  CLI --> Service["DeviceManager + shared services"]
  Service --> Win["WindowsBackend"]
  Service --> Lin["LinuxBackend"]
  Service --> Mac["MacOSBackend"]

  Win --> WMI["WMI (Win32_* queries)"]
  Win --> Libusb["libusb descriptor probe"]
  Win --> SPTD["IOCTL_SCSI_PASS_THROUGH_DIRECT"]

  Lin --> Lsblk["lsblk + sysfs + udevadm"]
  Lin --> Lsusb["lsusb / lsusb -v"]
  Lin --> DevNode["/dev/sdX access for poke/version"]

  Mac --> Prof["system_profiler SPUSBDataType"]
  Mac --> IOReg["ioreg mass-storage traversal"]
  Mac --> Diskutil["diskutil media-type fallback"]

  Service --> Version["Shared version probe + visibility rules"]
  Version --> Output["Deterministic text/JSON output"]
```

## Deep Dive

### 1. Cross-platform architecture with a shared contract

The CLI (`usb`) routes all operations through `DeviceManager`, which selects a backend implementation by platform. Each backend implements the same `scan_devices`, `poke_device`, and `sort_devices` contract, while shared service code handles version probing and output-field visibility rules. This keeps cross-platform behavior consistent without forcing lowest-common-denominator implementations.

### 2. Windows: native pass-through for device operations

Windows combines multiple data sources (WMI + libusb + driver metadata) to correlate USB identity, disk mapping, controller context, and read-only state. Poke operations use native `IOCTL_SCSI_PASS_THROUGH_DIRECT` against PhysicalDrive handles, which provides a stable pass-through path for validation scenarios that require direct command-level behavior.

### 3. Linux: multi-source correlation under privilege boundaries

Linux scanning fuses `lsblk`, sysfs, `udevadm`, and `lsusb` data, then normalizes it into a single device model. The probe path is parallelized for speed, and output includes transport and controller context when available. Poke operations require root/sudo access to block devices by design, so the runtime behavior remains explicit about privilege requirements.

### 4. macOS: enumeration-first strategy with explicit constraints

macOS uses `system_profiler` and `ioreg` to build device and mass-storage context, with `diskutil` fallback where media-type inference is ambiguous. Poke is intentionally disabled on macOS in the current implementation to avoid presenting partially reliable pass-through behavior as production-ready functionality.

### 5. Packaged for operational use

The project is distributed as MSI/PKG/DEB installers plus portable binaries so validation teams can run the CLI on test hosts without a local Python toolchain. The same codebase also ships as a Python package for integration with larger automation frameworks.

## Download (standalone builds)

Prebuilt installers and single-file binaries are published on GitHub Releases; Python is not required.

1. Download the latest asset for your OS:
   - **Windows**: `apricorn-usb-toolkit-<version>-x64.msi` installs to `%ProgramFiles%\Apricorn\Apricorn USB Toolkit\` and places `usb` on PATH (Admin required).
   - **Linux**: `apricorn-usb-toolkit-<version>-amd64.deb` installs to `/usr/local/lib/apricorn-usb-toolkit` and symlinks `/usr/local/bin/usb` (sudo required).<br>
                A portable `usb-linux.tar.gz` plus `installers/linux/install.sh` is available for non-Debian hosts.
   - **macOS**: `apricorn-usb-toolkit-<version>-macos.pkg` installs to `/usr/local/lib/apricorn-usb-toolkit` and exposes `/usr/local/bin/usb`; the payload is universal and the installer includes an opt-in choice for passwordless `sudo -n usb`. A raw `usb-macos.tar.gz` binary plus `installers/macos/install.sh` is also available for portable/manual use.
2. Run `usb` from a terminal with the commands below. Poke requires Administrator on Windows and sudo/root on Linux.
3. To update standalone builds, rerun the latest installer or download the newest portable binary. Standalone binaries do not use `usb-update`.

Detailed installer instructions (silent installs, manual uninstall, etc.) live in `INSTALLERS.md`.

## Install via pip

Recommended with Python 3.10+.

1. (Optional) create a virtual environment
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate
   ```
2. Install
   ```bash
   pip install .
   ```
3. For development
   ```bash
   uv sync --extra dev
   pre-commit install
   ```

## Usage

List Apricorn devices (VID 0984):
```bash
usb
```

<img src="output_example.png" alt="Apricorn USB Enumeration Example" width="700">

<br>
"Poke" device (make Green LED blink):

- Windows (Admin shell): target by index or `all`
  ```bash
  usb -p 1
  usb -p 1,3
  usb -p all
  ```
- Linux (sudo/root): target by index, block path, or `all`
  ```bash
  sudo usb -p 1
  sudo usb -p /dev/sdb
  sudo usb -p all
  ```
Script-friendly JSON:
```bash
usb --json
```
Outputs a deterministic structure tailored for automation:
```json
{
  "devices": [
    {
      "1": {
        "bcdUSB": 3.2,
        "idVendor": "0984",
        "idProduct": "1407",
        "bcdDevice": "0502",
        "iManufacturer": "Apricorn",
        "iProduct": "Secure Key 3.0",
        "iSerial": "147250000408",
        "SCSIDevice": false,
        "driverTransport": "BOT",
        "driveSizeGB": 16,
        "mediaType": "Basic Disk",
        "usbDriverProvider": "Apricorn",
        "usbDriverVersion": "21.46.5.13",
        "usbDriverInf": "oem17.inf",
        "diskDriverProvider": "Microsoft",
        "diskDriverVersion": "10.0.26100.7705",
        "diskDriverInf": "disk.inf",
        "usbController": "Intel",
        "busNumber": 1,
        "deviceAddress": 16,
        "physicalDriveNum": 3,
        "driveLetter": "F:",
        "readOnly": false,
        "scbPartNumber": "N/A",
        "hardwareVersion": "N/A",
        "modelID": "N/A",
        "mcuFW": "N/A"
      }
    }
  ]
}
```
If no devices are detected, `"devices"` is an empty list. This mode cannot be combined with `--poke`.

## Output Fields

The CLI prints normalized device fields. Typical keys include:
- `bcdUSB`: USB spec version (e.g., 2.0, 3.0)
- `idVendor`, `idProduct`: vendor/product IDs (lowercase hex)
- `bcdDevice`: device revision (4-hex digits)
- `iManufacturer`, `iProduct`, `iSerial`: user-friendly descriptors
- `driverTransport`: active transport classification such as `UAS`, `BOT`, `Vendor`, or `Unknown`
- `driveSizeGB`: normalized capacity or `N/A (OOB Mode)`
- `usbController`: Windows only (e.g., Intel, ASMedia)
- Platform identifiers: Windows physical drive number, Linux block path, macOS disk path

Visibility rules:
- Default text output hides `SCSIDevice` and `bridgeFW` on all platforms.
- Default Windows text output also hides `usbDriverProvider`, `usbDriverVersion`, `usbDriverInf`, `diskDriverProvider`, `diskDriverVersion`, `diskDriverInf`, `busNumber`, and `deviceAddress`.
- `usb --json` includes those Windows driver/debug fields.

Version details (best-effort, safely parsed from a vendor READ BUFFER):
- `scbPartNumber`, `hardwareVersion`, `modelID`, `mcuFW`

Additional visibility rules:
- The tool always hides `bridgeFW` from user output.
- If `bridgeFW` does not match `bcdDevice`, the version fields listed above are omitted.
- Devices reporting no size (OOB Mode) are automatically skipped for poke.

## Platform Notes

**Windows**
- Enumeration works as standard user; poke requires Administrator.
- Requires PowerShell in `PATH`. `libusb` and `pywin32` are pinned and installed via markers.

**Linux**
- Full detail may require root. Helpful tools: `lsusb`, `lsblk`, `udevadm`, and `lspci`.
- Optional helper: run `./update_sudoersd.sh` to allow passwordless reads for `lshw`/`fdisk -l` (review before using).
- Debian package installs can optionally add a passwordless `sudo usb` rule via `/etc/sudoers.d/usb-tool-nopasswd`; the interactive installer defaults to `No`.

**macOS**
- Enumeration uses `system_profiler` + `ioreg`. Poke is not yet enabled.
- For tests/tools: `brew install lsusb`.
- The macOS installer includes an opt-in choice for passwordless `sudo -n usb`. Manual installs can use `sudo /usr/local/lib/apricorn-usb-toolkit/update_sudoersd_macos.sh` after install.

## Python API

`find_apricorn_device()` is exported for convenience:
```python
from usb_tool import find_apricorn_device

devices = find_apricorn_device() or []
for dev in devices:
    print(dev.iProduct, dev.iSerial, dev.driveSizeGB)
```

Returned objects are `UsbDeviceInfo` dataclass instances from `src/usb_tool/models.py`.

Field sets are mostly shared across OSes, with some platform-specific attributes attached during shaping (for example `physicalDriveNum` on Windows or `blockDevice` on Linux/macOS). Version-field visibility rules are applied during device shaping, so hidden version fields are omitted from both CLI output and returned objects.

## Contributing / Dev

- Tooling is managed by `uv`; `pre-commit` runs the `uv`-managed `black`, `ruff`, and `mypy` commands.
- Refresh tool versions intentionally with `uv lock --upgrade-package black --upgrade-package ruff --upgrade-package mypy` or `uv lock --upgrade`, then commit the updated `uv.lock`.
- Tests: `pytest -q`.
- Python 3.10+.
