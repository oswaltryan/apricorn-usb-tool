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
