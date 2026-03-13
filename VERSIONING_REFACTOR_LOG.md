# Versioning Refactor Log

Date started: 2026-03-13
Status: Core refactor completed

## Goal

Move the repo to a single version source of truth in `pyproject.toml`, remove the checked-in `src/usb_tool/_cached_version.txt` mechanism, and automate version propagation so release/build/runtime behavior stays consistent without relying on a manually maintained secondary file.

## Current State

- `pyproject.toml` is now the only version source of truth.
- Runtime version resolution reads a guarded repo-local `pyproject.toml` before falling back to installed metadata.
- `scripts/project_version.py` reads and conditionally bumps `[project].version` in `pyproject.toml`.
- `.pre-commit-config.yaml` now runs the project-version bump hook.
- `.github/workflows/release.yaml` validates that a pushed `v*` tag matches `pyproject.toml`.

## Target State

- `pyproject.toml` is the only authoritative version source in the repo.
- Runtime version resolution prefers a guarded read of the repo-local `pyproject.toml` and falls back to installed package metadata.
- Installer/build scripts read the version from `pyproject.toml`.
- Release workflow validates the pushed tag against `pyproject.toml`.
- Version bumps are automated by updating `pyproject.toml` directly.
- `src/usb_tool/_cached_version.txt` and `scripts/sync_cached_version.py` are removed.

## Guardrails For `pyproject.toml`

When resolving a source-tree version, only trust a `pyproject.toml` if all checks pass:

- The file is discovered by walking upward from `src/usb_tool/_version.py`, not from `cwd`.
- `[project].name` is exactly `apricorn-usb-tool`.
- The repo root also contains `src/usb_tool`.

This avoids accidentally reading a parent or sibling project’s TOML.

## Refactor Plan

### 1. Runtime version resolution

Status: Completed

- Update `src/usb_tool/_version.py`.
- Resolution order:
  - `USB_TOOL_VERSION` environment override.
  - Guarded repo-local `pyproject.toml` parse when running from source.
  - `importlib.metadata.version("apricorn-usb-tool")`.
  - `"Unknown"` as the final fallback.
- Remove cache file reads/writes and `PKG-INFO` probing.

### 2. Build and installer version reads

Status: Completed

- Update:
  - `build/build_linux_installer.sh`
  - `build/build_macos_pkg.sh`
  - `build/build_windows_msi.ps1`
- Replace `_cached_version.txt` reads with `pyproject.toml` version reads.
- Keep platform-specific installer version normalization where required:
  - Debian version sanitization
  - macOS numeric `pkgbuild` version
  - MSI numeric version coercion

### 3. Release validation

Status: Completed

- Workflow now validates `github.ref_name` against `v<pyproject version>`.
- Cached-version workflow messaging has been removed.

### 4. Automation for version bumps

Status: Completed

- Cache-sync automation has been replaced with direct `pyproject.toml` version bump automation.
- `scripts/project_version.py bump-if-needed` updates only `[project].version`.
- The pre-commit hook now enforces the bump behavior at commit time.

### 5. Test updates

Status: Completed

- Replace `tests/test_version_cache.py` with tests for:
  - guarded `pyproject.toml` discovery
  - project-name validation
  - fallback to installed metadata
- Removed tests that assumed the cached file exists.

### 6. Cleanup

Status: Completed

- Remove:
  - `src/usb_tool/_cached_version.txt`
  - `scripts/sync_cached_version.py`
  - local pre-commit hook `sync-cached-version`
  - package-data inclusion for `_cached_version.txt`
- Update docs:
  - `DEVELOPMENT.md`
  - `README.md`
  - any installer docs referencing the old flow

## Risks

- Frozen/PyInstaller builds cannot rely on source-tree `pyproject.toml` being present at runtime.
- Bundled binaries now need `pyproject.toml` shipped with the PyInstaller payload.
- Tag validation and artifact naming must switch together to avoid mismatches.

## Open Decisions

- Decide whether to keep `USB_TOOL_VERSION` only for tests/builds or as a documented override.

## Confirmed Decisions

- `pyproject.toml` remains the single source of truth.
- Version bumping must remain automated on commit, not manual and not release-only.
- The automation should rewrite `[project].version` in `pyproject.toml` directly.
- The source-tree version guard must verify `[project].name == "apricorn-usb-tool"` before trusting a discovered `pyproject.toml`.

## Automated Bump Design

Status: Implemented

Keep the automation in Git's pre-commit flow, but change what it edits.

- Replace `scripts/sync_cached_version.py` with a new script that edits `pyproject.toml`.
- Keep a local `pre-commit` hook so the version is bumped automatically during commit attempts.
- Suggested behavior:
  - read the current version from working-tree `pyproject.toml`
  - read the previous committed version from `HEAD:pyproject.toml`
  - if the working-tree version already differs from `HEAD`, preserve it
  - if the working-tree version matches `HEAD`, bump the patch version in `pyproject.toml`
- Result:
  - ordinary commits automatically advance the version
  - intentional manual version changes are preserved
  - there is still only one version source in the repo

Notes:

- This preserves the current "every commit gets a new version" behavior the repo already expects.
- Pre-commit will modify `pyproject.toml`, so the first commit attempt may stop and require Git to re-stage the updated file before retrying. That is normal pre-commit behavior unless we move the bump to a different Git hook.
- If needed, we can later move the bump logic to a `prepare-commit-msg` or `pre-push` hook, but `pre-commit` is the closest match to the current repo behavior.

## Progress Entries

### 2026-03-13

- Reviewed the current version architecture across runtime, tests, build scripts, and release workflow.
- Replaced cache-file version resolution with guarded `pyproject.toml` reads plus metadata fallback.
- Added `scripts/project_version.py` and wired pre-commit to auto-bump `pyproject.toml` when it still matches `HEAD`.
- Updated installer scripts, PyInstaller specs, and release validation to read `pyproject.toml`.
- Removed `src/usb_tool/_cached_version.txt`, `scripts/sync_cached_version.py`, and the related package-data plumbing.
- Verified targeted versioning tests, YAML parsing, and Python compilation for changed files.
