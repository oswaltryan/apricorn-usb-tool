# Future‑Proof Cross‑Platform Plan for an `sg_raw`‑like Utility (USB‑only)

> **Scope:** Linux + Windows now; macOS later.
> **Device constraint:** Targets are **always USB** (MSC/UASP or your own USB device).
> **Goal:** A single codebase that can issue arbitrary **SCSI CDBs** to USB devices across platforms.

---

## ✅ Executive Summary

- **Primary backend:** Use **libusb‑1.0** as the only transport layer.
- **Device interface strategy:** Prefer a **vendor‑specific interface (class 0xFF)** on your device that you can safely claim on *all* OSes without conflicting with system storage drivers.
- **Transports to support:**
  - **Bulk‑Only Transport (BOT)** — protocol `0x50` (very common).
  - **UASP** — protocol `0x62` (USB 3.x, better performance & queueing).
- **CLI:** Provide a command that accepts raw CDB bytes and optional data-in/out length/files, similar to `sg_raw`.
- **Permissions & drivers:** Use udev rules (Linux), WinUSB binding (Windows), and leave room for macOS IOKit coexistence by avoiding OS mass‑storage drivers via a vendor interface.
- **Error model:** Auto‑issue **REQUEST SENSE** and present **Sense Key / ASC / ASCQ**; map transport vs. SCSI check conditions to clear return codes.
- **Fallback (optional):** If you must talk to generic MSC devices on Windows *without* re‑binding drivers, add a hidden **SPTI** backend (IOCTL_SCSI_PASS_THROUGH) behind the same CDB API.

---

## 1) Architecture

### 1.1 Components
- **Core library (Python package)**: Implements a **transport‑agnostic `send_cdb` API**:
  - Inputs: CDB bytes, direction (none/in/out), transfer length, timeout, LUN.
  - Outputs: status (OK / CHECK CONDITION / transport error), data (if any), sense buffer.
  - Implemented in Python 3.10+ using **PyUSB** or **ctypes/cffi** bindings to `libusb-1.0`.
- **Backends**:
  - **libusb‑BOT** (default; serialized commands initially)
  - **libusb‑UASP** (detected via interface protocol; can start serialized, add queueing later)
  - **(Optional) Windows SPTI** fallback via **pywin32** (same API; only when an MSC interface cannot be claimed by libusb).
- **CLI** (Python `argparse`; e.g., `usb_sgraw` or project CLI): Thin wrapper that parses args, calls the core API, and formats output (hex dumps, sense decoding, exit codes).

### 1.2 Why libusb?
- True cross‑platform API (Linux, Windows, macOS).
- Avoids kernel‑specific SCSI passthrough (SG_IO/SPTI/IOKit SCSITask), simplifying macOS later.
- Works best when you **control or can influence the device’s interfaces**.

---

## 2) Device / Interface Strategy (Key to Portability)

### 2.1 Best case: You control firmware
- Expose **two interfaces**:
  1) Normal MSC/UASP for OS usage (e.g., storage mount).
  2) **Vendor‑specific interface (class 0xFF)** for your tool.
- Your tool opens **only the vendor interface** via libusb → no driver conflicts and no unmount/eject dance.

### 2.2 If you don’t control firmware (generic MSC)
- **Linux/macOS:** You can (with privileges) **detach the kernel driver** and claim the MSC interface via libusb. This temporarily unmounts/ejects the disk.
- **Windows:** The MSC interface is bound to **usbstor**, which you generally **cannot claim** with libusb. You would need to:
  - Rebind that interface to **WinUSB** (e.g., via WCID descriptors or driver install), **or**
  - Use the **SPTI** fallback (see §8) and keep libusb as the primary path elsewhere.
- **Recommendation:** For predictable cross‑platform behavior, **design for a vendor‑specific interface** wherever possible.

---

## 3) USB Transport Details

### 3.1 Detecting transport & endpoints
- Identify the target **interface**:
  - `bInterfaceClass = 0x08` → Mass Storage (BOT/UASP)
  - `bInterfaceClass = 0xFF` → Vendor‑specific (your custom protocol can still encapsulate SCSI CDBs)
- Distinguish protocol via `bInterfaceProtocol`:
  - **BOT**: `0x50` (Bulk‑Only)
  - **UASP**: `0x62`
- Discover endpoints:
  - For **BOT**: one **Bulk‑OUT** (CBW + data‑out) and one **Bulk‑IN** (data‑in + CSW).
  - For **UASP**: Bulk‑IN/OUT **plus** Status (and possibly task mgmt) endpoints; supports stream IDs.

### 3.2 BOT (Bulk‑Only) state machine
1. **CBW (31 bytes)** → Bulk‑OUT
   - Signature `"USBC"`, Tag, DataTransferLength, Flags (IN=0x80 / OUT=0x00), LUN, CDB length, CDB bytes.
2. **Data** (optional)
   - OUT: host → device over Bulk‑OUT
   - IN: device → host over Bulk‑IN
3. **CSW (13 bytes)** → Bulk‑IN
   - Signature `"USBS"`, same Tag, residue, status (`0=Passed`, `1=Failed`, `2=Phase Error`).
4. On failure (`status!=0`): **REQUEST SENSE** to retrieve sense data (key/ASC/ASCQ).

### 3.3 UASP essentials
- Submit **Command IU** with stream ID, then handle **Data IU** and **Status IU**.
- You can **serialize** commands initially (single in‑flight) and add queueing later.

---

## 4) SCSI Layer (Baseline Commands)

Implement these first:
- `TEST UNIT READY (0x00)`
- `INQUIRY (0x12)` — vital product data (VPD optional).
- `REQUEST SENSE (0x03)` — auto‑issued on failure paths.
- `READ CAPACITY (10/16) (0x25/0x9E)`
- `READ(10) (0x28)` / `WRITE(10) (0x2A)` (for bigger I/O testing)

Provide sense decoding (Sense Key, ASC/ASCQ → friendly text).

---

## 5) CLI Design (sg_raw‑like)

**Example usage:**
```bash
usb_sgraw -d 0x1234:0x5678 --ifnum 1 --lun 0   --cdb "12 00 00 00 24 00" --din 36 --timeout-ms 10000 --bot
```

**Proposed flags:**
- `-d, --device <vid:pid | bus:addr | path>`
- `--ifnum <N>` (interface number to claim)
- `--lun <N>` (default 0)
- `--cdb "<hex bytes>"` (e.g., `"12 00 00 00 24 00"`)
- **Data transfer:**
  - `--din <N>` → read N bytes to stdout or `--dout-file <path>`
  - `--dout <path>` → write file contents to device (size = file length)
- **Transport & timing:**
  - `--bot` / `--uasp` / `--auto` (default auto)
  - `--timeout-ms <ms>` (default 30000)
- **I/O behavior:**
  - `--detach-kernel` (Linux/macOS only)
  - `--no-detach` (fail if interface is busy)
- **Output:**
  - `--hex` (hex dump responses)
  - `--sense` (always print sense if present)
  - `--quiet` / `--verbose`

Exit codes:
- `0` OK
- `2` SCSI **CHECK CONDITION** (sense available)
- `3` Transport error (USB stall/timeout/phase)
- `4` Parameter/usage error

---

## 6) Permissions & Driver Binding

- **Linux:**
  - Add a **udev rule** for your VID/PID to grant access to your user group; otherwise run as root.
  - If talking to generic MSC: either unmount volumes then `--detach-kernel`, or fail fast in safe mode.
- **Windows:**
  - For a **vendor interface**, present **WinUSB** via WCID descriptors or an INF installer so libusb can open it **without admin**.
  - Avoid trying to claim the system’s **usbstor** interface.
- **macOS (future):**
  - libusb works well when you’re **not** competing with Apple’s mass‑storage driver; using a vendor interface prevents conflicts.

---

## 7) Error Handling Contract

- Clearly separate **transport** vs **device/SCSI** errors.
- On non‑GOOD status or CSW status `1`, **auto REQUEST SENSE** and show:
  - **Sense Key / ASC / ASCQ** (and textual interpretation).
- For BOT short reads/writes, honor **residue** and report **actual** transfer length.
- Timeouts should include **which phase** timed out (CBW, Data‑IN/OUT, CSW, UASP IU).

---

## 8) Optional Windows Fallback (SPTI)

If you must communicate with **generic MSC devices** on Windows **without** re‑binding drivers, implement a backend that routes CDBs via **SPTI** (`DeviceIoControl` with `IOCTL_SCSI_PASS_THROUGH`). Keep the **same public CDB API** so the CLI/tooling stays unchanged. Use libusb everywhere else.

---

## 9) Test Matrix

- **BOT device** (USB 2.0 HDD enclosure) on Linux & Windows.
- **UASP device** (USB 3.x SSD enclosure) on Linux & Windows.
- With **mounted filesystem** (ensure safe behavior), and with device idle/unmounted.
- **Large transfers** (multi‑MB `READ(10)`), **short data‑in**, and **illegal request** to validate sense paths.
- Repeat the same matrix on **macOS** later with no code changes (vendor interface path).

---

## 10) Reference Pseudocode (BOT, single CDB)

```c
// Pseudocode (C-like); add error checks & retries in real code

libusb_context *ctx = NULL;
libusb_device_handle *h = NULL;

libusb_init(&ctx);
h = open_device(vid, pid);           // your helper
libusb_set_configuration(h, cfg);    // optional: if not already set
libusb_claim_interface(h, ifnum);

uint8_t ep_out = find_bulk_out(h, ifnum);
uint8_t ep_in  = find_bulk_in(h, ifnum);

struct CBW {
  uint32_t dCBWSignature;   // 'USBC' = 0x43425355
  uint32_t dCBWTag;
  uint32_t dCBWDataTransferLength;
  uint8_t  bmCBWFlags;      // 0x80 = IN, 0x00 = OUT
  uint8_t  bCBWLUN;
  uint8_t  bCBWCBLength;    // <= 16 for SCSI
  uint8_t  CBWCB[16];
} __attribute__((packed));

struct CSW {
  uint32_t dCSWSignature;   // 'USBS' = 0x53425355
  uint32_t dCSWTag;
  uint32_t dCSWDataResidue;
  uint8_t  bCSWStatus;      // 0=Passed, 1=Failed, 2=Phase Error
} __attribute__((packed));

struct CBW cbw = {
  .dCBWSignature = 0x43425355,
  .dCBWTag = next_tag(),
  .dCBWDataTransferLength = data_len,
  .bmCBWFlags = (dir_in ? 0x80 : 0x00),
  .bCBWLUN = lun,
  .bCBWCBLength = cdb_len
};
memcpy(cbw.CBWCB, cdb, cdb_len);

// 1) Send CBW
libusb_bulk_transfer(h, ep_out, (unsigned char*)&cbw, sizeof(cbw), &xfer, timeout_ms);

// 2) Data phase
if (dir_out) {
  libusb_bulk_transfer(h, ep_out, (unsigned char*)buf, data_len, &xfer, timeout_ms);
} else if (dir_in && data_len > 0) {
  libusb_bulk_transfer(h, ep_in, (unsigned char*)buf, data_len, &xfer, timeout_ms);
}

// 3) Read CSW
struct CSW csw;
libusb_bulk_transfer(h, ep_in, (unsigned char*)&csw, sizeof(csw), &xfer, timeout_ms);

// 4) If csw.bCSWStatus != 0 → issue REQUEST SENSE and decode
```

---


---

## 10b) Python-first Implementation Profile (Minimal Dependencies)

This project **assumes Python** as the primary implementation language and aims to keep runtime dependencies minimal.

### Stack
- **Python**: 3.10+
- **USB backend**: `libusb-1.0` (system library)
- **Bindings**: Either
  - **PyUSB** (thin wrapper on libusb), or
  - **ctypes/cffi** direct bindings to `libusb-1.0` (few hundred lines; eliminates a PyPI dep if desired)
- **Optional (Windows-only, fallback path)**: `pywin32` (for SPTI with `DeviceIoControl(IOCTL_SCSI_PASS_THROUGH)`), only if you choose to support the SPTI backend for generic MSC devices that you cannot claim with libusb.

### Install & packaging (recommendations)
- `pyproject.toml` with optional extras:
  - `usb` (default): PyUSB
  - `win-fallback`: pywin32
- Example:
  ```toml
  [project.optional-dependencies]
  usb = ["pyusb>=1.2"]
  win-fallback = ["pywin32>=306; platform_system=='Windows'"]
  ```
- For Windows packaging, ship `libusb-1.0.dll` alongside wheels or document installation.

### System prerequisites
- **Linux**: `libusb-1.0-0` (runtime), `libusb-1.0-0-dev` (dev). Add a udev rule for your VID/PID to allow non-root access if you’re using a vendor interface.
- **Windows**: Use **WinUSB** for the vendor-specific interface (WCID descriptors or driver package). No admin required to open the vendor interface.
- **macOS**: libusb via Homebrew (`brew install libusb`) for development. Vendor interface avoids races with Apple’s mass-storage driver.

### Permissions
- **Enumeration** typically works unprivileged. **Raw CDB data transfer** may require elevated permissions when talking to MSC interfaces claimed by the OS. Using a **vendor-specific interface** avoids this on all OSes.
- Provide an example **udev rule** (see §6) and a short **WinUSB** how-to (WCID).

### Minimal Python API
Provide a small transport-agnostic function surface (used by CLI and tests):
```python
from typing import Optional, Tuple

class ScsiError(Exception):
    def __init__(self, message: str, sense: bytes | None = None, transport: str | None = None):
        super().__init__(message)
        self.sense = sense or b""
        self.transport = transport or "bot"

def send_cdb(
    *, dev_handle,
    cdb: bytes,
    data_out: Optional[bytes] = None,
    data_in_len: int = 0,
    lun: int = 0,
    timeout_ms: int = 30000,
    transport: str = "auto",  # "bot" | "uasp" | "auto"
) -> Tuple[bytes, bytes]:
    """
    Sends a single SCSI CDB and returns (data_in, sense).
    Raise ScsiError on CHECK CONDITION (attach sense) or transport errors.
    Implementation selects BOT or UASP based on interface protocol when 'auto'.
    """
    ...
```

### PyUSB BOT sketch (single CDB, serialized)
```python
import usb.core, usb.util, struct, os

USBC = 0x43425355  # 'USBC'
USBS = 0x53425355  # 'USBS'

def _bulk_transfer(dev, ep, data, timeout):
    if isinstance(data, memoryview):
        data = data.tobytes()
    return dev.write(ep, data, timeout)

def _bulk_read(dev, ep, length, timeout):
    return bytes(dev.read(ep, length, timeout))

def send_cdb_bot(dev, ep_out, ep_in, cdb: bytes, data_out: bytes | None, data_in_len: int, lun: int, timeout_ms: int):
    tag = os.getpid() & 0xFFFFFFFF
    flags = 0x80 if data_in_len > 0 else 0x00
    dlen = data_in_len if data_in_len else (len(data_out) if data_out else 0)

    cbw = struct.pack(
        "<IIIBBB16s",
        USBC,            # dCBWSignature
        tag,             # dCBWTag
        dlen,            # dCBWDataTransferLength
        flags,           # bmCBWFlags
        lun & 0xFF,      # bCBWLUN
        len(cdb) & 0x1F, # bCBWCBLength (<=16 for SCSI)
        cdb.ljust(16, b"\x00"),
    )
    _bulk_transfer(dev, ep_out, cbw, timeout_ms)

    if data_out:
        _bulk_transfer(dev, ep_out, data_out, timeout_ms)
    elif data_in_len:
        data_in = _bulk_read(dev, ep_in, data_in_len, timeout_ms)
    else:
        data_in = b""

    csw = _bulk_read(dev, ep_in, 13, timeout_ms)
    # Unpack len-safely: pad to 16 to avoid struct errors
    pad = csw + b"\x00" * (16 - len(csw))
    dCSWSignature, dCSWTag, residue, status = struct.unpack("<I I I B", pad[:13] + b"\x00"*3)
    if dCSWSignature != USBS or dCSWTag != tag:
        raise ScsiError("Invalid CSW", transport="bot")

    if status != 0:
        # Auto REQUEST SENSE (0x03) 18 bytes
        sense = request_sense(dev, ep_out, ep_in, lun, timeout_ms)
        raise ScsiError("CHECK CONDITION", sense=sense, transport="bot")

    return data_in, b""

def request_sense(dev, ep_out, ep_in, lun, timeout_ms, alloc_len=18):
    cdb = bytes([0x03, 0x00, 0x00, 0x00, alloc_len, 0x00])
    data, _ = send_cdb_bot(dev, ep_out, ep_in, cdb, None, alloc_len, lun, timeout_ms)
    return data
```

### CLI shape (Python argparse)
```python
import argparse, sys

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-d","--device", help="vid:pid or bus:addr or path")
    ap.add_argument("--ifnum", type=int, default=0)
    ap.add_argument("--lun", type=int, default=0)
    ap.add_argument("--cdb", required=True, help='"12 00 00 00 24 00"')
    ap.add_argument("--din", type=int, default=0)
    ap.add_argument("--dout", help="file to send (data-out)")
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--transport", choices=["auto","bot","uasp"], default="auto")
    args = ap.parse_args(argv)

    # Resolve device & endpoints (helper not shown), then call send_cdb(...)
    # Print hex dump & sense on failure; return proper exit codes as per §5 & §7.
    ...

if __name__ == "__main__":
    sys.exit(main())
```

> Keep the **libusb-only** path as the default. Add the **Windows SPTI** fallback only if necessary, guarded behind a feature flag and an optional dependency.



## 11) Next Steps Checklist

- [ ] Decide **interface strategy** (vendor interface strongly recommended).
- [ ] Scaffold **core CDB API** + **libusb‑BOT** backend.
- [ ] Add **UASP** support (detect protocol `0x62`; serialize commands first).
- [ ] Build **CLI** (`usb_sgraw`) with the flags above.
- [ ] Implement **sense decoding** and return‑code mapping.
- [ ] Add **udev rule** template and **Windows WinUSB** notes (WCID).
- [ ] Create automated **test matrix** across Linux/Windows; later run the same on macOS.

---

*This plan is designed so you can add macOS by simply compiling against libusb and keeping to the vendor‑interface rule—no redesign required.*
