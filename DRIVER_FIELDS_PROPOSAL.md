# Driver Fields Proposal

## Goal

Extend the existing device info returned by the CLI and internal models to include driver information in a way that is:

- understandable to users
- consistent across Windows, Linux, and macOS
- tolerant of partial platform support through `N/A` values
- compatible with the current flat `key : value` CLI output

## Proposed Fields

The proposal has three output tiers:

- cross-platform base field: `driverTransport`
- default Windows-only USB-node fields: `usbDriverProvider`, `usbDriverVersion`, `usbDriverInf`
- Windows `--json`-only expanded fields: `diskDriverProvider`, `diskDriverVersion`, `diskDriverInf`, `busNumber`, `deviceAddress`

### Cross-Platform Base

Add `driverTransport` as the cross-platform driver field:

### `driverTransport`

High-level transport/protocol classification for the active storage path.

Example values:

- `UAS`
- `BOT`
- `Vendor`
- `Unknown`

This is the most important user-facing field because it explains how the device is currently attached at the driver level and is the only driver field with strong cross-platform diagnostic value.

### Windows Default Output

When running on Windows, include these USB-node fields in the default CLI output:

- `usbDriverProvider`
- `usbDriverVersion`
- `usbDriverInf`

These fields are useful in normal support workflows because they expose the Apricorn-bound USB driver package, which is the driver layer most relevant to selective suspend and related Windows USB issues.

### Windows Expanded JSON Output

When the user passes `--json` on Windows, include these additional fields:

- `diskDriverProvider`
- `diskDriverVersion`
- `diskDriverInf`
- `busNumber`
- `deviceAddress`

These fields are useful for deeper debugging, but they are not necessary in the default CLI output.

## Windows Driver Layering

Windows exposes these devices through multiple driver layers. For Apricorn support and troubleshooting, this distinction matters.

### Why Windows Needs Special Treatment

On Windows, a single Apricorn device commonly appears as at least two separate device nodes:

- a `USB` device node
- a `DiskDrive` child node

These nodes can show different driver providers, versions, and INF packages.

This is especially important because historical Apricorn issues such as selective suspend behavior are tied more closely to the USB node than to the disk-class child node.

### Recommendation For Windows

Keep `driverTransport` as the cross-platform field, but also expose Windows-specific layered driver details.

Primary Windows driver fields:

- `usbDriverProvider`
- `usbDriverVersion`
- `usbDriverInf`

Secondary Windows driver fields:

- `diskDriverProvider`
- `diskDriverVersion`
- `diskDriverInf`

Optional high-level transport field:

- `driverTransport`
  Example values: `UAS`, `BOT`, `Unknown`

### Display Strategy

Recommended default CLI behavior on Windows:

- show USB-node driver fields by default
- hide `busNumber` and `deviceAddress` by default
- show disk-node driver fields only when the user passes `--json`

This keeps the default output focused on the driver layer most relevant to Apricorn support while still preserving access to the storage-class layer for deeper debugging.

Recommended expanded-output behavior on Windows when the user passes `--json`:

- include disk-node driver fields
- include `busNumber`
- include `deviceAddress`

## Why This Shape

`driverTransport` is the right cross-platform field because it:

- directly answers the question most relevant to diagnostics
- maps cleanly across Windows, Linux, and macOS
- avoids low-value or noisy fields that frequently collapse to `N/A`
- gives users one clear signal instead of several OS-specific implementation details

Windows-specific USB-node and disk-node fields should be treated as an extension for deeper diagnostics rather than part of the cross-platform base.

## `SCSIDevice` Deprecation

### Current State

The project currently exposes `SCSIDevice` as a driver-adjacent field. In practice, this behaves as a limited transport hint and is not a complete description of driver state.

### Problem

`SCSIDevice` is ambiguous for users:

- it is not obvious whether it means UAS, SCSI passthrough capability, or general storage behavior
- it does not identify the actual bound driver
- it overlaps conceptually with the proposed `driverTransport` field

### Recommendation

Deprecate `SCSIDevice` in favor of `driverTransport`.

Mapping guidance:

- `SCSIDevice == True` typically becomes `driverTransport: UAS`
- `SCSIDevice == False` should not automatically imply `BOT`; use `Unknown` unless the backend can verify the actual transport

### Suggested Rollout

1. Add `driverTransport`.
2. Keep `SCSIDevice` temporarily for backward compatibility.
3. Stop showing `SCSIDevice` in default CLI output once the new fields are present.
4. Keep `SCSIDevice` in serialized/internal output for one compatibility window if needed.
5. Remove `SCSIDevice` entirely after downstream consumers have migrated.

### Compatibility Note

If backward compatibility matters for scripts or tests, `SCSIDevice` should remain populated internally during the transition, but the new driver fields should become the canonical source of truth.

## Sample CLI Output

### Windows

```text
Found 1 Apricorn device(s):

=== Apricorn Device #1 ===
  bcdUSB            : 3.0
  idVendor          : 0984
  idProduct         : 1407
  bcdDevice         : 0300
  iManufacturer     : Apricorn
  iProduct          : Secure Key 3.0
  iSerial           : ABCD123456
  driveSizeGB       : 64
  mediaType         : Removable Media
  driverTransport   : BOT
  usbDriverProvider : Apricorn
  usbDriverVersion  : 21.46.5.13
  usbDriverInf      : oem17.inf
  usbController     : Intel
  physicalDriveNum  : 2
  driveLetter       : E:
  readOnly          : False
```

### Linux

```text
=== Apricorn Device #1 ===
  bcdUSB           : 3.0
  idVendor         : 0984
  idProduct        : 1407
  bcdDevice        : 0300
  iManufacturer    : Apricorn
  iProduct         : Secure Key 3.0
  iSerial          : ABCD123456
  driveSizeGB      : 64
  mediaType        : Removable Media
  driverTransport  : UAS
  blockDevice      : /dev/sdb
  readOnly         : False
```

### macOS

```text
=== Apricorn Device #1 ===
  bcdUSB           : 3.0
  idVendor         : 0984
  idProduct        : 1407
  bcdDevice        : 0300
  iManufacturer    : Apricorn
  iProduct         : Secure Key 3.0
  iSerial          : ABCD123456
  driveSizeGB      : 64
  mediaType        : Removable Media
  driverTransport  : UAS
  blockDevice      : disk4
```

## Data Expectations By Platform

### Windows

- `driverTransport`: likely derivable from the active USB/storage binding
- `usbDriverProvider`: should be available
- `usbDriverVersion`: should usually be available
- `usbDriverInf`: should be available
- `diskDriverProvider`: should be available when expanded output is requested
- `diskDriverVersion`: should usually be available when expanded output is requested
- `diskDriverInf`: should be available when expanded output is requested

### Linux

- `driverTransport`: derivable from kernel driver binding such as `uas` vs `usb-storage`

### macOS

- `driverTransport`: derivable in many cases from the active stack

## Recommendation Summary

Use the following as the cross-platform driver info contract:

- `driverTransport`

Deprecate `SCSIDevice` and replace it in user-facing output with `driverTransport`.

On Windows, extend that base with layered driver details:

- `usbDriverProvider`
- `usbDriverVersion`
- `usbDriverInf`
- `diskDriverProvider`
- `diskDriverVersion`
- `diskDriverInf`

For default Windows CLI output, prefer the USB-node driver fields because they are the most relevant to Apricorn-specific behavior such as selective suspend issues.

Disk-node driver fields should only be emitted when the user explicitly requests expanded output through `--json`.

On Windows, `busNumber` and `deviceAddress` should also only be emitted when the user explicitly requests expanded output through `--json`.

## Implementation Notes

This proposal can be implemented within the existing project structure. No new top-level module is required.

### Existing Files To Update

Core model and output shaping:

- `src/usb_tool/models.py`
  Add the new optional fields:
  - `driverTransport`
  - `usbDriverProvider`
  - `usbDriverVersion`
  - `usbDriverInf`
  - `diskDriverProvider`
  - `diskDriverVersion`
  - `diskDriverInf`

- `src/usb_tool/cli.py`
  Update list output so:
  - `driverTransport` is shown cross-platform
  - Windows default output includes `usbDriverProvider`, `usbDriverVersion`, and `usbDriverInf`
  - Windows `--json` output includes the expanded Windows-only fields
  - Windows default output hides `diskDriverProvider`, `diskDriverVersion`, `diskDriverInf`, `busNumber`, and `deviceAddress`

Windows backend:

- `src/usb_tool/backend/windows.py`
  Add logic to collect:
  - USB-node signed driver metadata
  - disk-node signed driver metadata
  - transport classification for `driverTransport`

  This is the primary implementation file for the Windows-specific work.

Linux backend:

- `src/usb_tool/backend/linux.py`
  Populate only:
  - `driverTransport`

  No Linux-specific driver metadata fields are needed in default output or JSON for this proposal.

macOS backend:

- `src/usb_tool/backend/macos.py`
  Populate only:
  - `driverTransport`

  No macOS-specific driver metadata fields are needed in default output or JSON for this proposal.

Tests:

- `tests/test_windows_usb.py`
  Add or update tests for:
  - USB-node driver field population
  - disk-node driver field population
  - `driverTransport`

- `tests/test_linux_usb.py`
  Add or update tests for `driverTransport`

- `tests/test_mac_usb.py`
  Add or update tests for `driverTransport`

- `tests/test_cross_usb.py`
  Add or update output-shaping tests for:
  - default Windows output
  - Windows `--json` output
  - omission of JSON-only Windows fields from normal CLI output

### New File Requirement

No new file is required for the base implementation.

If the Windows driver queries become large enough to justify extraction, an optional follow-up refactor could introduce a helper module such as:

- `src/usb_tool/backend/windows_driver_info.py`

That refactor is optional, not required for the initial implementation.

### Project Structure If No New File Is Added

```text
src/
  usb_tool/
    cli.py
    models.py
    backend/
      windows.py
      linux.py
      macos.py
tests/
  test_cross_usb.py
  test_windows_usb.py
  test_linux_usb.py
  test_mac_usb.py
```

### Optional Project Structure If Windows Driver Logic Is Extracted Later

```text
src/
  usb_tool/
    cli.py
    models.py
    backend/
      windows.py
      windows_driver_info.py
      linux.py
      macos.py
tests/
  test_cross_usb.py
  test_windows_usb.py
  test_linux_usb.py
  test_mac_usb.py
```

### Recommended Implementation Order

1. Extend `UsbDeviceInfo` in `src/usb_tool/models.py`.
2. Implement Windows USB-node and disk-node driver collection in `src/usb_tool/backend/windows.py`.
3. Populate `driverTransport` in `src/usb_tool/backend/linux.py` and `src/usb_tool/backend/macos.py`.
4. Update output shaping in `src/usb_tool/cli.py`.
5. Add or update tests in `tests/`.

## Updated Windows Sample Output

```text
Found 1 Apricorn device(s):

=== Apricorn Device #1 ===
  bcdUSB            : 3.0
  idVendor          : 0984
  idProduct         : 1407
  bcdDevice         : 0300
  iManufacturer     : Apricorn
  iProduct          : Secure Key 3.0
  iSerial           : ABCD123456
  driveSizeGB       : 64
  mediaType         : Removable Media
  driverTransport   : BOT
  usbDriverProvider : Apricorn
  usbDriverVersion  : 21.46.5.13
  usbDriverInf      : oem17.inf
  usbController     : Intel
  physicalDriveNum  : 2
  driveLetter       : E:
  readOnly          : False
```

## Windows Extended Output Example

If the user passes `--json`, both Windows driver layers can be included. In that case, the same device could look like this:

```text
=== Apricorn Device #1 ===
  bcdUSB             : 3.0
  idVendor           : 0984
  idProduct          : 1407
  bcdDevice          : 0300
  iManufacturer      : Apricorn
  iProduct           : Secure Key 3.0
  iSerial            : ABCD123456
  driveSizeGB        : 64
  mediaType          : Removable Media
  driverTransport    : BOT
  usbDriverProvider  : Apricorn
  usbDriverVersion   : 21.46.5.13
  usbDriverInf       : oem17.inf
  diskDriverProvider : Microsoft
  diskDriverVersion  : 10.0.26100.7705
  diskDriverInf      : disk.inf
  usbController      : Intel
  busNumber          : 1
  deviceAddress      : 3
  physicalDriveNum   : 2
  driveLetter        : E:
  readOnly           : False
```
