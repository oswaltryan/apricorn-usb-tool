# Development Notes

## Windows Scan Profiling

`usb --profile-scan` is a developer/support diagnostic aid for Windows scan performance.

- It writes timing and drive-letter resolution diagnostics to `stderr`.
- It does not change normal device output or JSON payloads.
- It is intended for troubleshooting and regression analysis, not normal user workflows.

Example:

```powershell
usb --profile-scan 2> profile.txt
```

When run from PowerShell or `cmd.exe`, the packaged Windows executable should not require
`USB_TOOL_NO_PAUSE`. That environment variable is only a fallback workaround if pause
detection is misbehaving on a specific machine.

The output includes:

- `windows-scan-profile`: coarse timing for major Windows scan stages
- `windows-drive-letter-profile`: bulk WMI drive-letter resolution details and fallback usage

When a scan retries because Windows returned mismatched discovery lists, diagnostics include `pass=1` and `pass=2` so duplicate output is attributable to the retry path.

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
