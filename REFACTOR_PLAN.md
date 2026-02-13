# Refactor Plan Checklist

Goal: move to a clean, testable, cross-platform architecture with explicit OS backends while preserving CLI behavior and output stability.

**Phase 0: Prep**
- [x] Capture baseline CLI output for `usb -h`, `usb`, and `usb --json` on each OS available.
- [x] Run `pytest -q` and save current results.
- [x] Identify any behavior that must remain stable (output fields, sorting, error messages).

**Phase 0: Verification**
- [x] `git status -sb` shows a clean working tree.
- [x] Baseline outputs for `usb -h`, `usb`, and `usb --json` are saved per OS.
- [x] `pytest -q` output is saved (baseline).

**Phase 1: Scaffolding**
- [x] Add `src/usb_tool/` with empty skeleton modules that mirror the target layout:
- [x] `src/usb_tool/cli.py`
- [x] `src/usb_tool/backend/base.py`
- [x] `src/usb_tool/backend/windows.py`
- [x] `src/usb_tool/backend/linux.py`
- [x] `src/usb_tool/backend/macos.py`
- [x] `src/usb_tool/services.py`
- [x] `src/usb_tool/models.py`
- [x] `src/usb_tool/exceptions.py`
- [x] `src/usb_tool/help_text.py`
- [x] `src/usb_tool/constants.py`
- [x] `src/usb_tool/utils.py`
- [x] `src/usb_tool/device_config.py`
- [x] `src/usb_tool/_version.py`
- [x] `src/usb_tool/_cached_version.txt`

**Phase 1: Verification**
- [x] `rg --files -g "src/usb_tool/**"` lists the expected module files.
- [x] `python -c "import usb_tool; print(usb_tool.__file__)"` resolves to `src/usb_tool`.

**Phase 2: Port Core CLI**
- [x] Move argument parsing and command dispatch from `usb_tool/cross_usb.py` into `src/usb_tool/cli.py`.
- [x] Keep CLI flags and output identical (same wording, ordering, and JSON structure).
- [x] Preserve double-click behavior for Windows and consistent exit codes.

**Phase 2: Verification**
- [x] `usb -h` output matches baseline (diff check).
- [x] `usb` output fields and ordering match baseline for the same devices.
- [x] `usb --json` structure matches baseline for the same devices.
- [x] Windows double-click pause behavior verified manually.
- [x] `usb --json --poke` exits non-zero.

**Phase 3: Create Backend Contracts**
- [x] Implement `AbstractBackend` in `src/usb_tool/backend/base.py` with `scan_devices()` and `poke_device()`.
- [x] Move Windows logic from `usb_tool/windows_usb.py` into `src/usb_tool/backend/windows.py`.
- [x] Move Linux logic from `usb_tool/linux_usb.py` into `src/usb_tool/backend/linux.py`.
- [x] Move macOS logic from `usb_tool/mac_usb.py` into `src/usb_tool/backend/macos.py`.
- [x] Keep macOS poke disabled end-to-end unless explicitly enabled later.

**Phase 3: Verification**
- [x] `AbstractBackend` is abstract and backends expose `scan_devices()` and `poke_device()`.
- [x] macOS `usb -p` returns the expected disabled message.
- [x] Windows/Linux `usb -p` works on a known device with admin/root.

**Phase 4: Shared Services + Models**
- [x] Create `DeviceManager` in `src/usb_tool/services.py` to orchestrate scan, sort, and poke.
- [x] Define `UsbDeviceInfo` dataclass in `src/usb_tool/models.py` and align fields with current output.
- [x] Consolidate constants and helper parsing into `constants.py` and `utils.py`.
- [x] Move `device_config.py`, `_version.py`, and `_cached_version.txt` under `src/usb_tool/`.

**Phase 4: Verification**
- [x] `python -c "from usb_tool.services import DeviceManager; DeviceManager().list_devices()"` runs without import errors.
- [x] `UsbDeviceInfo` fields match baseline output keys.
- [x] `pytest -q tests/test_utils.py` passes.

**Phase 5: Packaging + Build**
- [x] Update `pyproject.toml` to use `package-dir = {"" = "src"}` and set `packages = ["usb_tool"]`.
- [x] Switch entrypoint to `usb = "usb_tool.cli:main"`.
- [x] Update `build/*.spec` and installer scripts to use `src/usb_tool/...` paths.
- [x] Ensure `_cached_version.txt` is included in package data.

**Phase 5: Verification**
- [x] `pyproject.toml` contains `package-dir = {"" = "src"}` and `usb = "usb_tool.cli:main"`.
- [x] Build specs reference `src/usb_tool/cli.py` and `src/usb_tool/_cached_version.txt`.
- [x] Build scripts produce artifacts without path errors.

**Phase 6: Tests and Fixtures**
- [x] Migrate or add unit tests for parsing and target selection in `tests/`.
- [x] Update test imports to point at `src/usb_tool/...`.
- [x] Refresh mock-data fixtures via `tests/collect_*` scripts if needed.

**Phase 6: Verification**
- [x] `pytest -q` passes.
- [x] Collectors run without import errors on each OS.
- [x] No tests import legacy modules (e.g., `rg -n "usb_tool\\.cross_usb|usb_tool\\.windows_usb|usb_tool\\.linux_usb|usb_tool\\.mac_usb|usb_tool\\.common" tests` returns empty).

**Phase 7: Cutover**
- [x] Remove legacy `usb_tool/` package directory once parity is verified.
- [x] Verify CLI outputs match baseline on each OS.
- [x] Tag a pre-release if desired (e.g., `v1.3.0-rc1`) for validation.

**Phase 7: Verification**
- [x] `rg --files -g "usb_tool/**"` returns no legacy package files.
- [x] `usb -h`, `usb`, and `usb --json` match baselines.
- [x] `usb -p` behavior matches baseline (Windows/Linux) and macOS refusal.

**Final Validation**
- [x] `pytest -q`
- [x] `usb -h` output matches baseline.
- [x] `usb` output field set and ordering unchanged.
- [x] `usb --json` payload structure unchanged.
- [x] `usb -p` behavior unchanged on Windows/Linux; macOS refuses poke.

**Rollback**
- [ ] If parity fails, revert to `main` and keep the refactor branch for incremental fixes.
