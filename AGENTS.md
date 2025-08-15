### **Refactoring Plan: `usb-tool`**

This document outlines a strategic plan to refactor the `usb-tool` project. The primary goals are to modernize the project structure, simplify complex logic, improve code clarity, and enhance testability, all while preserving the existing functionality.

---

### **Phase 1: Project Modernization and Cleanup**

**Goal:** Establish a clean, modern, and unambiguous project structure by consolidating packaging configuration and organizing source code.

1.  **Unify Packaging with `pyproject.toml`:**
    *   **Action:** Migrate all packaging metadata and dependency specifications from `setup.py` and `requirements.txt` into `pyproject.toml`. The `[project]` and `[project.scripts]` tables in `pyproject.toml` can fully replace `setup.py`.
    *   **Rationale:** `pyproject.toml` is the modern standard for Python packaging (PEP 518, PEP 621). A single configuration file simplifies maintenance and reduces redundancy. OS-specific dependencies will be handled using environment markers.
    *   **Example (`pyproject.toml` dependencies):**
        ```toml
        [project]
        # ... other metadata
        dependencies = [
            "pywin32 >= 309; sys_platform == 'win32'",
            "libusb >= 1.0.27; sys_platform == 'win32'"
        ]
        ```

2.  **Clean Up Root Directory:**
    *   **Action:** Delete the now-redundant `setup.py` and `requirements.txt` files. Remove the `usb_tool.egg-info` and `win_usb_tool.egg-info` directories to prevent confusion from past builds.
    *   **Rationale:** This removes clutter and ensures that the build system uses a single source of truth (`pyproject.toml`).

3.  **Introduce a Common Utilities Module:**
    *   **Action:** Create a new file: `usb_tool/utils.py`.
    *   **Action:** Move the following duplicated helper functions from `linux_usb.py`, `mac_usb.py`, and `windows_usb.py` into the new `utils.py` module:
        *   `bytes_to_gb()`
        *   `find_closest()`
        *   `parse_usb_version()` (from `windows_usb.py` and `linux_usb.py`)
    *   **Action:** Update the platform-specific modules to import these functions from `usb_tool.utils`.
    *   **Rationale:** This adheres to the Don't Repeat Yourself (DRY) principle, making the code easier to maintain and ensuring consistent behavior across platforms.

---

### **Phase 2: Refactoring the Core Application (`cross_usb.py`)**

**Goal:** Improve the structure and readability of the main command-line entry point by breaking down its complex logic into smaller, single-responsibility functions.

1.  **Decompose the `main` Function:**
    *   **Action:** Extract the command-handling logic from `main` into two separate functions:
        *   `_handle_list_action(devices: list)`: Contains the logic to print the details of all discovered devices.
        *   `_handle_poke_action(args: argparse.Namespace, devices: list)`: Contains all logic for the `--poke` command, including privilege checks, target parsing, and execution.
    *   **Rationale:** The `main` function should only be responsible for orchestrating the application flow: parsing arguments, discovering devices, and dispatching to the correct handler. This separation of concerns makes the code easier to read and test.

2.  **Isolate Poke Target Parsing Logic:**
    *   **Action:** Within `_handle_poke_action`, create a new helper function: `_parse_poke_targets(poke_input: str, devices: list) -> list`.
    *   **Action:** Move the complex logic for parsing the `--poke` argument (handling "all", comma-separated indices, device paths, and OOB device filtering) into this new function. It will return a clean list of validated targets to poke.
    *   **Rationale:** This isolates a complex and critical piece of logic, making it independently testable and easier to understand.

3.  **Centralize Platform-Specific Sorting:**
    *   **Action:** Move the device sorting logic from `main` into the respective platform-specific modules (`windows_usb.py`, `linux_usb.py`).
    *   **Action:** Each platform module will expose a `sort_devices(devices: list) -> list` function. `cross_usb.py` will import and call the correct one.
    *   **Rationale:** Device sorting criteria are platform-dependent. This change places the platform-specific logic where it belongs, cleaning up the cross-platform entry point.

---

### **Phase 3: Refactoring Platform-Specific Modules**

**Goal:** Improve the robustness, clarity, and maintainability of the data gathering and correlation logic within each OS-specific module.

1.  **For `windows_usb.py`:**
    *   **Action:** Refactor the data correlation logic. Instead of relying on the order of multiple lists (`sort_wmi_drives`, `sort_libusb_data`), create a primary dictionary of devices keyed by a unique identifier (e.g., the serial number from `Win32_PnPEntity`). Iterate through other data sources (libusb, WMI disk drives) to enrich the data for each device in the dictionary.
    *   **Rationale:** Relying on list order is fragile and can break if a single query returns devices in a different order. A dictionary lookup based on a stable key is significantly more robust.

2.  **For `linux_usb.py`:**
    *   **Action:** Encapsulate all `subprocess.run` calls into a single, robust helper function within the module: `_run_command(cmd: list) -> subprocess.CompletedProcess`. This helper will contain standardized error handling for `FileNotFoundError`, `TimeoutExpired`, and non-zero return codes.
    *   **Action:** Refactor the data gathering to use a serial-number-keyed dictionary, similar to the Windows refactoring, to make correlation between `lsusb`, `lsblk`, and `lshw` outputs more reliable.
    *   **Rationale:** This reduces code duplication and centralizes command execution logic, making it easier to manage and debug.

3.  **For `mac_usb.py`:**
    *   **Action:** Replace the `ioreg` and `awk` shell command with a more Python-native approach. First, parse the JSON output from `system_profiler SPUSBDataType -json`. Then, use `ioreg` to get UAS information, but parse its output within Python to avoid a complex and brittle shell script.
    *   **Action:** Fix the bug where `mediaType` is assigned but not defined in the `macOSUsbDeviceInfo` dataclass.
    *   **Rationale:** Parsing structured data like JSON directly in Python is far more reliable and maintainable than processing text with external tools like `awk`.

---

### **Phase 4: Enhancing Documentation and Testing**

**Goal:** Ensure the refactored codebase is easy for future developers to understand, use, and extend, and is protected against regressions.

1.  **Improve Code Documentation:**
    *   **Action:** Add comprehensive, Google-style docstrings to all refactored and newly created functions and modules. Explain the purpose, arguments, and return values.
    *   **Action:** Ensure full type hinting is applied across the codebase for improved static analysis and readability.
    *   **Action:** Add inline comments to clarify any non-obvious or complex logic, especially within the data parsing and correlation sections.

2.  **Expand Test Coverage:**
    *   **Action:** Write new unit tests for all extracted helper functions (e.g., `_parse_poke_targets`, the utility functions, and command runners).
    *   **Action:** Create dedicated test files with mocked data for the refactored correlation logic in each platform-specific module. Test edge cases like missing serial numbers, extra devices not matching, and devices in OOB mode.
    *   **Action:** Write integration-level tests for the main `cross_usb.py` workflows, mocking the `find_apricorn_device` and `send_scsi_read10` calls to verify argument parsing and handler dispatching.

3.  **Update Project README:**
    *   **Action:** Update the project's `README.md` file to reflect the simplified installation process using only `pip install .` (which relies on `pyproject.toml`).
    *   **Action:** Add a brief section for developers explaining the new project structure and the roles of the key modules.