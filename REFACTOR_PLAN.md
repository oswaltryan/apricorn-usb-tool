# Refactor Plan Checklist

Goal: move to a clean, testable, cross-platform architecture with explicit OS backends while preserving CLI behavior and output stability.

**Phase 0: Prep**
- [ ] Create a new branch from `main` (e.g., `refactor/structure-v2`).
- [ ] Capture baseline CLI output for `usb -h`, `usb`, and `usb --json` on each OS available.
- [ ] Run `pytest -q` and save current results.
- [ ] Identify any behavior that must remain stable (output fields, sorting, error messages).

**Phase 0: Verification**
- [ ] `git status -sb` shows a clean working tree.
- [ ] Baseline outputs for `usb -h`, `usb`, and `usb --json` are saved per OS.
- [ ] `pytest -q` output is saved (baseline).

**Phase 1: Scaffolding**
- [ ] Add `src/usb_tool/` with empty skeleton modules that mirror the target layout:
- [ ] `src/usb_tool/cli.py`
- [ ] `src/usb_tool/backend/base.py`
- [ ] `src/usb_tool/backend/windows.py`
- [ ] `src/usb_tool/backend/linux.py`
- [ ] `src/usb_tool/backend/macos.py`
- [ ] `src/usb_tool/services.py`
- [ ] `src/usb_tool/models.py`
- [ ] `src/usb_tool/exceptions.py`
- [ ] `src/usb_tool/help_text.py`
- [ ] `src/usb_tool/constants.py`
- [ ] `src/usb_tool/utils.py`
- [ ] `src/usb_tool/device_config.py`
- [ ] `src/usb_tool/_version.py`
- [ ] `src/usb_tool/_cached_version.txt`

**Phase 1: Verification**
- [ ] `rg --files -g "src/usb_tool/**"` lists the expected module files.
- [ ] `python -c "import usb_tool; print(usb_tool.__file__)"` resolves to `src/usb_tool`.

**Phase 2: Port Core CLI**
- [ ] Move argument parsing and command dispatch from `usb_tool/cross_usb.py` into `src/usb_tool/cli.py`.
- [ ] Keep CLI flags and output identical (same wording, ordering, and JSON structure).
- [ ] Preserve double-click behavior for Windows and consistent exit codes.

**Phase 2: Verification**
- [ ] `usb -h` output matches baseline (diff check).
- [ ] `usb` output fields and ordering match baseline for the same devices.
- [ ] `usb --json` structure matches baseline for the same devices.
- [ ] Windows double-click pause behavior verified manually.
- [ ] `usb --json --poke` exits non-zero.

**Phase 3: Create Backend Contracts**
- [ ] Implement `AbstractBackend` in `src/usb_tool/backend/base.py` with `scan_devices()` and `poke_device()`.
- [ ] Move Windows logic from `usb_tool/windows_usb.py` into `src/usb_tool/backend/windows.py`.
- [ ] Move Linux logic from `usb_tool/linux_usb.py` into `src/usb_tool/backend/linux.py`.
- [ ] Move macOS logic from `usb_tool/mac_usb.py` into `src/usb_tool/backend/macos.py`.
- [ ] Keep macOS poke disabled end-to-end unless explicitly enabled later.

**Phase 3: Verification**
- [ ] `AbstractBackend` is abstract and backends expose `scan_devices()` and `poke_device()`.
- [ ] macOS `usb -p` returns the expected disabled message.
- [ ] Windows/Linux `usb -p` works on a known device with admin/root.

**Phase 4: Shared Services + Models**
- [ ] Create `DeviceManager` in `src/usb_tool/services.py` to orchestrate scan, sort, and poke.
- [ ] Define `UsbDeviceInfo` dataclass in `src/usb_tool/models.py` and align fields with current output.
- [ ] Consolidate constants and helper parsing into `constants.py` and `utils.py`.
- [ ] Move `device_config.py`, `_version.py`, and `_cached_version.txt` under `src/usb_tool/`.

**Phase 4: Verification**
- [ ] `python -c "from usb_tool.services import DeviceManager; DeviceManager().list_devices()"` runs without import errors.
- [ ] `UsbDeviceInfo` fields match baseline output keys.
- [ ] `pytest -q tests/test_utils.py` passes.

**Phase 5: Packaging + Build**
- [ ] Update `pyproject.toml` to use `package-dir = {"" = "src"}` and set `packages = ["usb_tool"]`.
- [ ] Switch entrypoint to `usb = "usb_tool.cli:main"`.
- [ ] Update `build/*.spec` and installer scripts to use `src/usb_tool/...` paths.
- [ ] Ensure `_cached_version.txt` is included in package data.

**Phase 5: Verification**
- [ ] `pyproject.toml` contains `package-dir = {"" = "src"}` and `usb = "usb_tool.cli:main"`.
- [ ] Build specs reference `src/usb_tool/cli.py` and `src/usb_tool/_cached_version.txt`.
- [ ] Build scripts produce artifacts without path errors.

**Phase 6: Tests and Fixtures**
- [ ] Migrate or add unit tests for parsing and target selection in `tests/`.
- [ ] Update test imports to point at `src/usb_tool/...`.
- [ ] Refresh mock-data fixtures via `tests/collect_*` scripts if needed.

**Phase 6: Verification**
- [ ] `pytest -q` passes.
- [ ] Collectors run without import errors on each OS.
- [ ] No tests import legacy modules (e.g., `rg -n "usb_tool\\.cross_usb|usb_tool\\.windows_usb|usb_tool\\.linux_usb|usb_tool\\.mac_usb|usb_tool\\.common" tests` returns empty).

**Phase 7: Cutover**
- [ ] Remove legacy `usb_tool/` package directory once parity is verified.
- [ ] Verify CLI outputs match baseline on each OS.
- [ ] Tag a pre-release if desired (e.g., `v1.3.0-rc1`) for validation.

**Phase 7: Verification**
- [ ] `rg --files -g "usb_tool/**"` returns no legacy package files.
- [ ] `usb -h`, `usb`, and `usb --json` match baselines.
- [ ] `usb -p` behavior matches baseline (Windows/Linux) and macOS refusal.

**Final Validation**
- [ ] `pytest -q`
- [ ] `usb -h` output matches baseline.
- [ ] `usb` output field set and ordering unchanged.
- [ ] `usb --json` payload structure unchanged.
- [ ] `usb -p` behavior unchanged on Windows/Linux; macOS refuses poke.

**Rollback**
- [ ] If parity fails, revert to `main` and keep the refactor branch for incremental fixes.
