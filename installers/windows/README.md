# Windows Installer

Builds a Windows Installer (`.msi`) that installs the `usb` CLI under `%ProgramFiles%\Apricorn\Apricorn USB Tool` and exposes it system-wide via PATH.

## Prerequisites

- Windows 10/11 build machine
- [WiX Toolset 3.14+](https://wixtoolset.org/) available in `PATH` (`candle.exe`, `light.exe`)
- PowerShell 5.1+ or PowerShell 7+
- Python 3.10+ (used to build the PyInstaller binary and read the project version)

## Build Instructions

1. Build the PyInstaller executable (or let the helper do it):
   ```powershell
   build\build_windows.bat
   ```
2. Create the MSI artifact via the helper script (runs PyInstaller automatically when needed):
   ```powershell
   pwsh build\build_windows_msi.ps1
   ```
   Skip PyInstaller if the executable is already in dist\
   ```powershell
   pwsh build\build_windows_msi.ps1 -SkipPyInstaller
   ```
3. The resulting `usb-tool-<version>-x64.msi` is placed in `dist/` ready for distribution.

The MSI installs only the CLI—no shortcuts or Start Menu entries are created. Uninstall via **Settings → Apps → Apricorn USB Tool**.
