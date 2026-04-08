# AGENTS.md

> A concise, agent-oriented guide to hacking on this project.

You are working on **apricorn-usb-toolkit**, a cross-platform USB utility for Apricorn devices. The project exposes a single CLI, `usb`, that enumerates Apricorn USB hardware and can issue a safe diagnostic "poke" on supported platforms.

Use this file as the quick project map. Treat the current repo contents as the source of truth.

---

## Ground Rules

1. **Primary objective**: keep enumeration and diagnostics reliable across Windows, Linux, and macOS.
2. **Platform boundaries matter**: keep OS-specific behavior in backend modules; keep the CLI thin.
3. **Do not follow missing docs**: there is no `INSTRUCTIONS.md` in this repo. Use `README.md`, `INSTALLERS.md`, and the current repo contents instead.
4. **Examples are illustrative**: adapt names, imports, and structure to the current codebase.
5. **CLI text is part of the contract**: help text, human-readable output, JSON shape, and error messages are covered by tests.

---

## Project Snapshot

- Package name: **apricorn-usb-toolkit**
- Python: **3.10+**
- Source root: `src/usb_tool/`
- CLI entrypoint:
  - `usb` -> `usb_tool.cli:main`
- Library helper:
  - `find_apricorn_device()` -> `usb_tool.__init__`
- Platforms:
  - **Windows**: enumeration + poke
  - **Linux**: enumeration + poke
  - **macOS**: enumeration only; CLI poke intentionally rejected

### Current module layout

- `src/usb_tool/cli.py`
  - CLI argument parsing, `--json`, hidden `--profile-scan`, poke target parsing, formatted output, Windows pause-on-exit behavior for packaged builds.
- `src/usb_tool/help_text.py`
  - Platform-specific man-page-style help output.
- `src/usb_tool/services.py`
  - `DeviceManager`, backend selection, version-field visibility rules, device-version population helpers.
- `src/usb_tool/backend/base.py`
  - `AbstractBackend` interface.
- `src/usb_tool/backend/windows.py`
  - Windows enumeration via WMI/libusb and Windows poke implementation.
- `src/usb_tool/backend/linux.py`
  - Linux enumeration using `lshw`, `lsblk`, `udevadm`, `lsusb`, and `lspci`; the Linux CLI poke path currently lives here and is implemented as a minimal block-device open check in this tree.
- `src/usb_tool/backend/macos.py`
  - macOS enumeration via `system_profiler`, `ioreg`, and `diskutil`; poke raises a clear "not supported" error.
- `src/usb_tool/models.py`
  - Shared `UsbDeviceInfo` dataclass. Platform-specific fields are attached dynamically where needed.
- `src/usb_tool/device_version.py`
  - Best-effort Apricorn version probe via READ BUFFER / OS-specific device access.
- `src/usb_tool/device_config.py`
  - PID/revision-to-product-hint and capacity normalization data.
- `src/usb_tool/constants.py`
  - Shared constants such as excluded PIDs.
- `src/usb_tool/utils.py`
  - Helpers such as bytes-to-GB conversion and closest-size matching.

### Compatibility note

`usb_tool.windows_usb`, `usb_tool.linux_usb`, and `usb_tool.mac_usb` are compatibility aliases exposed by `src/usb_tool/__init__.py`; the real implementations live under `src/usb_tool/backend/`.

---

## Setup

Recommended developer setup uses `uv`:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv sync --extra dev
pre-commit install
```

Editable installs also work:

```bash
python -m pip install -U pip
python -m pip install -e .[dev]
pre-commit install
```

### OS prerequisites

**Windows**

- Enumeration works as a normal user.
- Poke requires **Administrator**.
- Runtime deps come from `pyproject.toml` markers: `pyusb`, `libusb`, `pywin32`, and `pygments` on Windows.
- PowerShell is expected in `PATH`.

**Linux**

- Enumeration depends on standard system tools used by the backend: `lsusb`, `lsblk`, `udevadm`, `lspci`, and currently `lshw`.
- Recommend installing at least `usbutils` and `lshw`; the rest usually come from base system packages.
- Poke and some low-level access paths typically require **root/sudo**.
- Optional helper from repo root:
  ```bash
  sudo ./update_sudoersd.sh
  ```

**macOS**

- Enumeration uses built-in tools: `system_profiler`, `ioreg`, and `diskutil`.
- For tests and some utilities: `brew install lsusb`
- Optional helper from repo root:
  ```bash
  sudo ./update_sudoersd_macos.sh
  ```
- The installed helper path used by the macOS installer is `/usr/local/lib/apricorn-usb-toolkit/update_sudoersd_macos.sh`.

---

## Run / Dev

```bash
# List devices
usb

# Script-friendly JSON
usb --json

# Windows poke (Administrator)
usb -p 1
usb -p 1,3
usb -p all

# Linux poke (sudo/root)
sudo usb -p 1
sudo usb -p /dev/sdb
sudo usb -p all
```

Additional behavior:

- `usb -h` prints platform-specific help text.
- `usb --json` and `usb --poke` are mutually exclusive.
- `usb --profile-scan` exists as a **hidden developer diagnostic flag**.
- macOS rejects `--poke` before scanning with a clear CLI error.

There is **no** `usb-update` entrypoint in the current tree.

---

## Tests

Run the full test suite with:

```bash
uv run --extra dev pytest -q
```

Quality checks used by local hooks and CI:

- `black`
- `ruff`
- `ruff format`
- `mypy`
- `pytest`

Relevant test files include:

- `tests/test_cross_usb.py`
- `tests/test_help_text.py`
- `tests/test_linux_usb.py`
- `tests/test_mac_usb.py`
- `tests/test_windows_usb.py`
- `tests/test_version_visibility.py`
- `tests/test_cli_pause.py`
- `tests/test_package_imports.py`

Mock-data collectors:

- `tests/collect_windows_data.py`
- `tests/collect_linux_data.py`
- `tests/collect_macOS_data.py`
- `tests/mock_data/mock_data_collection_instructions.md`

---

## Agent-Relevant Structure

- `usb_tool.cli._parse_poke_targets()`
  - Parses index targets on Windows and index or `/dev/...` targets on Linux.
  - OOB devices are skipped automatically.
- `usb_tool.services.DeviceManager`
  - Selects the platform backend and applies backend-specific sorting.
- `usb_tool.services.populate_device_version()`
  - Fills optional Apricorn version fields.
- `usb_tool.services.prune_hidden_version_fields()`
  - Hides version fields when the visibility rules do not pass.
- `backend/*.sort_devices()`
  - Stable ordering is important for CLI output and tests.

### Current backend behavior

**Windows backend**

- Uses WMI plus libusb data to shape `UsbDeviceInfo`.
- Includes expanded JSON-only driver metadata.
- Sorts by physical drive ordering.

**Linux backend**

- Correlates `lsblk`, `udevadm`, `lsusb`, controller data, and current `lshw` transport hints.
- Adds `blockDevice`, `usbController`, and `readOnly`.
- Sorts by block-device path.

**macOS backend**

- Correlates `system_profiler` output with `ioreg` mass-storage data.
- Adds `blockDevice`, `usbController`, and `readOnly` when available.
- Sorts by disk path, then serial fallback.
- Poke is intentionally unsupported from the CLI.

---

## Configuration / Assumptions

- Apricorn filtering is based on VID `0984`.
- Known non-target PIDs are excluded via `src/usb_tool/constants.py`:
  - `0221`
  - `0211`
  - `0301`
- Size normalization uses `src/usb_tool/device_config.py` and `utils.find_closest()`.
- Devices reporting `N/A (OOB Mode)` are skipped for poke.
- Version fields are best-effort and may be hidden if bridge/revision consistency checks fail.

---

## Commands And UX

- `usb`
  - Prints normalized device fields in human-readable form.
- `usb --json`
  - Emits deterministic JSON for automation.
- `usb -p <targets>`
  - Runs the diagnostic poke on Windows/Linux only.
- `usb --profile-scan`
  - Hidden developer-only profiling output on stderr.

Text output intentionally hides some fields that JSON may include, especially Windows driver/debug fields.

---

## Security And Safety

- Never introduce write-type SCSI commands without explicit review.
- Poke must remain non-destructive.
- On Windows, poke should fail cleanly when not elevated.
- On Linux, raw block-device access generally requires `sudo/root`.
- On macOS, keep poke disabled unless end-to-end support is intentionally implemented and gated.
- Review sudoers helper scripts before changing installer or privilege behavior.

---

## Conventions And Gotchas

- Keep platform-specific code under `src/usb_tool/backend/`.
- Keep `src/usb_tool/cli.py` focused on argument parsing, validation, and output.
- If you touch output fields, check both text and JSON behavior.
- If you touch help/error text, run the help/CLI tests.
- Be careful with Windows serial normalization, especially `MSFT30...` handling.
- Respect OOB mode.
- Prefer deterministic ordering and stable field visibility.
- Avoid eager platform imports in shared modules; there is targeted test coverage that importing `usb_tool` does not eagerly import the Windows backend.

---

## What To Do When Adding Features

1. Start with tests when the change is parser, shaping, or CLI-contract related.
2. Touch one backend at a time unless the feature is intentionally cross-platform.
3. Update `device_config.py` when new Apricorn PIDs or size mappings are introduced.
4. Keep JSON and human-readable output contracts in sync with tests and docs.
5. Run the relevant `uv run --extra dev pytest ...` target, then the full suite if the change is broad.

---

## Quick Triage Checklist

- Capture `usb` or `usb --json` output, the OS, and whether the shell was elevated.
- If poke is involved, note whether the device was OOB.
- On Linux, verify the presence of `lsusb`, `lsblk`, `udevadm`, `lspci`, and current `lshw` behavior.
- On Windows, confirm Administrator status and PowerShell availability.
- On macOS, collect `system_profiler`/`ioreg`-based fixtures with `tests/collect_macOS_data.py`.
- Add or refresh sanitized fixtures under `tests/mock_data/` when fixing parser/correlation bugs.

---

Keep it safe, cross-platform, and boringly reliable.
