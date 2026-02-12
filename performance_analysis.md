# USB-Tool Performance Investigation (Windows)

Date: 2026-02-12
Host: Windows (local)
Repo: C:\Users\ROswalt\Desktop\apricorn-usb-tool

## Goal
Identify the main sources of slow execution on Windows and capture baseline timings with a connected device.

## Plan (lowest risk)
1. Measure end-to-end runtime of `usb` (no code changes).
2. Time each major data source call independently via a lightweight profiling script:
   - WMI USB devices (`Win32_PnPEntity`)
   - WMI USB drives (`Win32_DiskDrive`)
   - PowerShell controller mapping
   - libusb enumeration
   - Physical drive mapping (WMI)
   - PowerShell read-only map
   - Per-device drive-letter lookup
3. Use the timings to decide whether to consolidate PowerShell/WMI calls and reduce per-device PowerShell invocations.

## Baseline: End-to-End Runtime
`python -m usb_tool.cross_usb`
- TotalSeconds: **3.469s**

## Component Timings (single run)
Captured via direct calls to `usb_tool.windows_usb` functions.

- `get_wmi_usb_devices`: **0.370s** (len=1)
- `get_wmi_usb_drives`: **0.011s** (len=1)
- `get_all_usb_controller_names` (PowerShell): **1.493s** (len=1)
- `get_apricorn_libusb_data`: **0.031s** (len=1)
- `get_physical_drive_number`: **0.008s** (len=1)
- `get_usb_readonly_status_map` (PowerShell): **1.598s** (len=0)
- `get_drive_letter_via_ps` per device:
  - idx=1: **0.368s** → Not Formatted

## Initial Findings
- PowerShell subprocesses dominate:
  - Controller mapping (`get_all_usb_controller_names`) and read-only map (`get_usb_readonly_status_map`) each cost ~1.5s.
  - Per-device drive letter lookup is ~0.37s *per device*.
- WMI queries and libusb enumeration are relatively fast in this run.

## Next Steps (proposed)
1. Replace per-device PowerShell drive-letter lookups with a single batched query.
2. Cache or combine PowerShell queries to avoid multiple PowerShell startups per run.
3. If needed, re-run timings after each change to quantify improvements.

---

## Update: Batched Drive-Letter Query (2026-02-12)
Implemented a single batched PowerShell query (`get_drive_letters_map`) and removed
per-device `get_drive_letter_via_ps` calls.

### Baseline: End-to-End Runtime (after change)
`python -m usb_tool.cross_usb`
- TotalSeconds: **3.663s**

### Component Timings (single run, after change)
- `get_wmi_usb_devices`: **0.315s** (len=1)
- `get_wmi_usb_drives`: **0.011s** (len=1)
- `get_all_usb_controller_names` (PowerShell): **1.513s** (len=1)
- `get_apricorn_libusb_data`: **0.027s** (len=1)
- `get_physical_drive_number`: **0.008s** (len=1)
- `get_usb_readonly_status_map` (PowerShell): **0.991s** (len=0)
- `get_drive_letters_map` (PowerShell): **0.515s** (len=2)

### Notes
- The batched query removes per-device scaling. On hosts with multiple devices,
  this should be a net win, even though the single batched call still costs ~0.5s.
- The largest remaining cost is still PowerShell startup and JSON conversion,
  specifically controller mapping and read-only map.

---

## Update: Consolidated PowerShell Calls (2026-02-12)
Combined controller mapping, USB read-only status, and drive letters into a single
PowerShell invocation (`get_ps_usb_metadata`).

### Baseline: End-to-End Runtime (after change)
`python -m usb_tool.cross_usb`
- TotalSeconds: **3.052s**

### Component Timings (single run, after change)
- `get_wmi_usb_devices`: **0.331s** (len=1)
- `get_wmi_usb_drives`: **0.012s** (len=1)
- `get_apricorn_libusb_data`: **0.030s** (len=1)
- `get_physical_drive_number`: **0.008s** (len=1)
- `get_ps_usb_metadata` (PowerShell): **2.366s** (len=3)

### Notes
- Consolidation reduced the total runtime by ~0.4s on this host versus the prior run,
  primarily by removing separate PowerShell startups.
- PowerShell remains the dominant cost; further wins likely require reducing PS use
  or replacing with WMI/COM calls.

## Raw Output
PROFILE_RESULTS_START
get_wmi_usb_devices: 0.370s ok=True len=1
get_wmi_usb_drives: 0.011s ok=True len=1
get_all_usb_controller_names: 1.493s ok=True len=1
get_apricorn_libusb_data: 0.031s ok=True len=1
get_physical_drive_number: 0.008s ok=True len=1
get_usb_readonly_status_map: 1.598s ok=True len=0
get_drive_letter_via_ps_per_device
  idx=1 0.368s -> Not Formatted
PROFILE_RESULTS_END

