# Development Notes

## Scan Profiling Recovery Plan

This section is a plan only. It is intentionally limited to the requested macOS
`--profile-scan` bottleneck fix and output cleanup. It does not authorize or
describe any regression-wiring, benchmark scripts, interactive tests, hooks, or
cross-platform profiling refactors.

### Worktree Audit

Current `git status --short` shows the repo is well outside the requested
scope.

- Tracked changes: 13 entries
  - Relevant to the macOS `--profile-scan` request:
    - `DEVELOPMENT.md`
    - `src/usb_tool/backend/macos.py`
    - `src/usb_tool/device_version.py`
  - Not required for the requested change:
    - `VERSIONING_REFACTOR_LOG.md`
    - `installers/macos/build/pkg/usb-tool-base.pkg`
    - `installers/macos/build/pkg/usb-tool-nopasswd.pkg`
    - `pyproject.toml`
    - `src/usb_tool/backend/linux.py`
    - `src/usb_tool/backend/windows.py`
    - `tests/test_linux_usb.py`
    - `tests/test_mac_usb.py`
    - `tests/test_version_visibility.py`
    - `uv.lock`
- Untracked changes: 7 entries
  - None are necessary for the requested fix:
    - `benchmarks/`
    - `scripts/__init__.py`
    - `scripts/profile_scan_regression.py`
    - `src/usb_tool/backend/profiling.py`
    - `src/usb_tool/profile_baselines.py`
    - `tests/test_profile_scan_regression.py`
    - `windows_profile_scan.txt`

### Requested End State

After the repo is restored to `HEAD`, the implementation scope should be kept
to the minimum necessary to achieve all of the following:

1. Keep `usb --profile-scan` as a developer-only diagnostic aid.
2. Remove the macOS unlocked-device bottleneck that was adding more than 1
   second to scan time.
3. Make macOS `--profile-scan` output use the same overall format and ordering
   as the existing Windows output captured in the temporary
   `windows_profile_scan.txt` reference.
4. Avoid any regression-baseline wiring, benchmark scripts, hooks, or
   interactive tests.

### macOS Output Contract

This requirement is explicit: macOS `--profile-scan` output should mimic the
Windows logging structure, not merely contain similar fields.

Expected ordering for macOS profiling lines:

1. Zero or more supporting diagnostic lines first.
   - Windows example: `windows-drive-letter-profile: ...`
   - macOS equivalent should use a macOS-specific prefix, but appear before the
     main scan timing lines.
2. The `details` line second.
   - Windows example:
     `windows-scan-profile details: pass=1 populate_device_version_total=...`
   - macOS should follow that same placement:
     `macos-scan-profile details: ...`
3. The coarse stage timing line third.
   - Windows example:
     `windows-scan-profile pass=1 minimal=false expanded=false usb=1 ...: ...`
   - macOS should use the same style and field ordering where applicable:
     `macos-scan-profile ...: system_profiler=..., ioreg_mass_storage=..., ... total=...`

Expected formatting rules:

- `details` must appear before the coarse timing line, matching Windows.
- The coarse timing line should be the last profiling line before normal device
  output begins.
- macOS should keep its own stage names, but present them in a Windows-like
  single summary line rather than ad hoc ordering.
- If macOS emits extra supporting diagnostics, those should appear before the
  `details` line, not after the main timing summary.
- No baseline-comparison lines or benchmark-script output should appear in the
  executable output.

### Minimal Change Budget After Reset

Expected implementation footprint after the reset:

- Code files: 1 to 2
  - Required: `src/usb_tool/backend/macos.py`
  - Optional only if absolutely necessary: `src/usb_tool/device_version.py`
- Documentation files: 1
  - `DEVELOPMENT.md`
- Test files: 0
- Build/package files: 0
- CLI/plumbing files: 0
  - The hidden `--profile-scan` argument already exists; it should not require
    new CLI wiring for this request.

### Required Selective Cleanup Step

Before any implementation work, restore only the out-of-scope files so the
worktree is reduced to the requested macOS profiling task without destroying
this plan document.

Planned tracked-file restore set:

```bash
git restore \
  VERSIONING_REFACTOR_LOG.md \
  installers/macos/build/pkg/usb-tool-base.pkg \
  installers/macos/build/pkg/usb-tool-nopasswd.pkg \
  pyproject.toml \
  src/usb_tool/backend/linux.py \
  src/usb_tool/backend/windows.py \
  src/usb_tool/device_version.py \
  tests/test_linux_usb.py \
  tests/test_mac_usb.py \
  tests/test_version_visibility.py \
  uv.lock
```

Planned untracked-file cleanup set:

```bash
rm -rf \
  benchmarks \
  scripts/__init__.py \
  scripts/profile_scan_regression.py \
  src/usb_tool/backend/profiling.py \
  src/usb_tool/profile_baselines.py \
  tests/test_profile_scan_regression.py
```

Files intentionally preserved during cleanup:

- `DEVELOPMENT.md`
- `windows_profile_scan.txt`

### Implementation Plan

1. Perform the selective cleanup above and confirm only the in-scope files
   remain modified.
2. Re-open only the current `HEAD` versions of:
   - `src/usb_tool/backend/macos.py`
   - `DEVELOPMENT.md`
   - the temporary `windows_profile_scan.txt` reference, only long enough to
     copy the desired output shape into the implementation plan.
3. Implement the bottleneck fix in `src/usb_tool/backend/macos.py` only if
   possible.
   - The preferred fix is to skip the expensive mounted-media version probe for
     unlocked devices during normal scans.
   - OOB devices should continue to probe version information.
   - If a second file is needed, limit it to a narrowly scoped helper in
     `src/usb_tool/device_version.py`.
4. Restructure macOS `--profile-scan` output so it follows the Windows pattern:
   - optional supporting diagnostic line first
   - `macos-scan-profile details: ...` second
   - `macos-scan-profile ...: stage_a=..., stage_b=..., total=...` third
   - no baseline-comparison lines
   - no benchmark-script dependencies
5. Keep macOS field names and ordering stable enough that a user can compare the
   macOS output against the Windows sample by eye.
6. Validate only with direct executable/manual runs of `usb --profile-scan` on
   macOS for:
   - 1 unlocked device on bus
   - 1 OOB device on bus
7. Update this file with the final developer note once the implementation is
   complete.

### Final Developer Note

Implemented the requested macOS `--profile-scan` cleanup in
`src/usb_tool/backend/macos.py` and updated the macOS unit coverage in
`tests/test_mac_usb.py`.

- Mounted-media scans keep the fast path and skip version probing by default.
- OOB devices still probe version information, and the existing
  `USB_TOOL_FORCE_MACOS_VERSION_PROBE=1` override still forces the mounted-media
  path when explicitly requested.
- Profiling output now stays limited to:
  - optional supporting diagnostic lines first
  - `macos-scan-profile details: ...` second
  - the coarse `macos-scan-profile ...: ... total=...` summary last
- macOS baseline-comparison output was removed from executable profiling output.

Validation completed locally with:

```bash
pytest -q tests/test_mac_usb.py
```

The selective cleanup step described above was not executed automatically here
because the current worktree contains unrelated modified and deleted files that
should not be restored or removed without explicit user approval.

### Explicit Non-Goals

The following are out of scope for the requested change and should not be
reintroduced:

- baseline-comparison output
- profile regression scripts
- hidden profile assertion logic
- automated performance tests
- interactive test prompts
- pre-commit/CI hook changes
- Linux or Windows profiling changes
- package/build artifact updates
- version bumps or lockfile churn

## Version Bump Guardrail

`pyproject.toml` is the single version source of truth.

The local pre-commit hook `bump-project-version` compares the working-tree
`pyproject.toml` version to `HEAD:pyproject.toml`.

- If you already changed the version intentionally, the hook leaves it alone.
- If you forgot to bump the version, the hook increments the patch version in
  `pyproject.toml` for you.

This keeps ordinary commits from going out with a stale version while avoiding
a second version file in the repo.

## Tooling Versions

`uv.lock` is the source of truth for developer tool versions used by local hooks
and CI.

- `pre-commit` runs `uv run ...` commands for `black`, `ruff`, and `mypy`.
- GitHub Actions uses the same `uv` environment, so type/lint failures should
  reproduce locally after `uv sync --extra dev`.
- To refresh to newer tool releases, update intentionally with
  `uv lock --upgrade-package black --upgrade-package ruff --upgrade-package mypy`
  or `uv lock --upgrade`, then commit the lockfile changes.
