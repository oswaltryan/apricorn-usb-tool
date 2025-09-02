# AGENTS.md

> A concise, agent‑oriented guide to hacking on this project.
> Format reference: **AGENTS.md open format**.

You are an expert Python developer tasked with enhancing a **cross‑platform USB utility for Apricorn devices**. The project exposes a CLI (`usb`) that **enumerates Apricorn USB hardware** and (on supported OSes) can **send a safe SCSI READ(10) “poke”** for diagnostics.

Your job is to apply the logic from the refactoring/architecture plan in **INSTRUCTIONS.md** to this codebase, keeping platform boundaries clean and behavior consistent.

---

## Ground rules

1. **Primary objective**: robust, accurate enumeration + diagnostics across Windows, Linux, and (read‑only for now) macOS.
2. **Examples are illustrative**: any code snippets you see in issues/docs are patterns, not drop‑ins.
3. **Integrate intelligently**: adapt names, imports, and structure to existing modules.
4. **Follow INSTRUCTIONS.md**: its design tenets win when in doubt.

---

## Project snapshot

- Name: **usb-tool** (Cross‑platform USB tool for Apricorn devices)
- CLI entrypoints:
  - `usb` → `usb_tool.cross_usb:main`
  - `usb-update` → `usb_tool.update:main`
- Python: **3.10+**
- Platforms: **Windows / Linux** (poke supported), **macOS** (enumeration; poke planned)
- Key modules (under `usb_tool/`):
  - `cross_usb.py` — cross‑platform CLI, argument parsing, dispatch, poke target parsing.
  - `windows_usb.py` / `linux_usb.py` / `mac_usb.py` — OS adapters for discovery & shaping data.
  - `poke_device.py` — **portable SCSI READ(10)** via `ctypes` (Windows SPTD, Linux SG_IO, macOS DKIOCSCSIUSERCMD).
  - `utils.py` — helpers (bytes→GB, closest‑size, BCD parsing).
  - `device_config.py` — PID/REV → product hints + standard capacities.
  - `update.py` — self‑update for editable installs.
- Examples: `examples/` (pollers, auto‑lock test).
- Tests: `tests/` (unit + mock‑data collectors per OS).

---

## Setup

### 0) Clone & dev install
```bash
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
python -m pip install -U pip
python -m pip install -e .[dev]   # installs ruff, black, pytest, pre-commit
pre-commit install
```

### 1) OS prerequisites

**Windows**
- Run enum-only tasks as a normal user; **poke requires Administrator**.
- Runtime deps (`pywin32`, `libusb`) are pinned for `win32` via `pyproject.toml`.
- PowerShell available in PATH (used by some helpers).

**Linux**
- Recommend: `sudo apt install usbutils lshw` (or equivalent) for `lsusb`/`lshw`.
- Poke/advanced scan often require **root**. Optionally install sudoers drop‑in from repo root:
  ```bash
  sudo ./update_sudoersd.sh
  ```
  (grants passwordless `lshw`/`fdisk -l /dev/sdX` reads; review before use).

**macOS**
- For tests and some utilities: `brew install lsusb`
- Poke path exists in `poke_device.py`, but end‑to‑end CLI poke is **currently disabled**; future‑enable here.

---

## Run / Dev

```bash
# List devices (Apricorn VID 0984), no elevated perms needed on most setups
usb

# Poke (safe READ(10)): **Admin on Windows**, **root/sudo on Linux**
# Windows: target by displayed index number (e.g., 1 or 1,3 or 'all')
usb -p 1

# Linux: target by index or by /dev path
sudo usb -p 1,/dev/sdb
sudo usb -p all

# Self-update (editable installs / Git checkout)
usb-update
```

CLI help is printed with `usb -h` on any OS.

---

## Tests

```bash
pytest -q
```

- Tests emphasize **pure parsing** and **target selection** (see `tests/`).
- Mock‑data collectors live in `tests/collect_*.py`. See `tests/mock_data/mock_data_collection_instructions.md` for capturing live OS snapshots that back unit tests.
- CI hygiene: **all pre‑commit hooks must pass** (black, ruff, pytest).

---

## Agent‑relevant project structure

- `usb_tool/cross_usb.py`
  - Orchestrates: scan → pretty‑print OR poke workflow.
  - Validates targets via `_parse_poke_targets()` (index vs. path differs per OS).
  - Restricts poke to **Windows/Linux** for now.
- `usb_tool/windows_usb.py`
  - WMI for devices/drives, libusb for descriptors, PS helpers for drive letters & read‑only status.
  - Shapes into `WinUsbDeviceInfo`; sorts by `physicalDriveNum`.
- `usb_tool/linux_usb.py`
  - `lsusb` + `lsusb -v` (details), `lshw` (UAS driver), `lsblk` (size/serial).
  - Correlates via **serial** and **block device path**; shapes `LinuxUsbDeviceInfo`.
- `usb_tool/mac_usb.py`
  - `system_profiler` + `ioreg` (UAS). Read‑only enumeration; shapes `macOSUsbDeviceInfo`.
- `usb_tool/poke_device.py`
  - Unified `send_scsi_read10(device_identifier, ...)` using per‑OS IOCTLs with `ctypes`.
  - Non‑destructive; returns bytes read or raises `ScsiError` with rich context.
- `usb_tool/device_config.py`
  - Maps PID/`bcdDevice` → `("Product Hint", [standard capacities GB])` for nearest‑size matching.
- `examples/`
  - Small utilities for polling/experiments (Windows/mac variants).
- `update_sudoersd.sh`, `usb_tool_sudoers`
  - Optional Linux convenience for unprivileged scanning; **review before applying**.

---

## Configuration / assumptions

- **USB‑only** devices (guaranteed): code already filters for Apricorn VID **0984** and excludes known non‑targets (e.g., `0221`, `0301`).
- Size normalization uses `device_config.closest_values` via `utils.find_closest`.
- OOB devices report **N/A size** and are **skipped for poke** automatically.

---

## Commands & UX (what users see)

- `usb` → prints normalized per‑device fields (VID/PID, Serial, Product, USB version, Device rev, Size, UAS, bus/dev addr or block path, controller/drive letter where applicable).
- `usb -p <targets>` → attempts READ(10), prints per‑target status; refuses on macOS for now with clear message.
- `usb-update` → pulls & reinstalls if running from a Git checkout (editable).

---

## Security & safety

- **Never commit secrets**.
- **Poke** uses **READ(10)** only (non‑destructive). Do **not** introduce write‑type SCSI ops without explicit review.
- On Linux/macOS, raw device access requires **root**; on Windows, **Administrator**. Fail with friendly errors.
- Review `usb_tool_sudoers` before installing; adjust devices/paths for your environment.

---

## Conventions & gotchas

- Keep **platform‑specific code in platform modules**; keep `cross_usb.py` thin.
- Respect `OOB` (size unknown) = **skip poke**.
- Be careful with serial correlation (e.g., Windows `MSFT30…` prefix); see existing logic.
- Message text matters; CLI output is part of UX and is used by tests.
- Prefer **deterministic sorting** (`sort_devices(...)`) per OS for stable output & tests.

---

## What to do when adding features

1. **Start with tests** (extend existing patterns in `tests/`). For any new parser, add pure‑function tests first.
2. **Extend `device_config.py`** when adding PIDs or REV codes; keep list tight and documented.
3. **Touch one OS adapter at a time**; keep cross‑OS feature parity in `cross_usb.py`.
4. **Run pre‑commit hooks** locally before pushing.

---

## Future tracks (from INSTRUCTIONS.md)

- Enable macOS poke via `DKIOCSCSIUSERCMD` end‑to‑end with safe gating & clear errors.
- Optional: richer JSON output mode (`usb --json`) for automation.
- Optional: structured logs for lab runs (attach bus/addr, controller, UAS driver).

---

## Quick triage checklist

- Repro a user report with `usb` output (attach OS, Admin/root status, and whether device shows OOB).
- If Linux: verify `lsusb`, `lsblk`, `lshw` availability; check sudoers helpers.
- If Windows: confirm Administrator session; confirm PowerShell present.
- Gather mock snapshots via `tests/collect_*.py` and commit sanitized fixtures to `tests/mock_data/`.

---

Happy hacking! Keep it safe, cross‑platform, and boringly reliable. 🛠️🔌
