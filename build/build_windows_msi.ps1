[CmdletBinding()]
param(
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot '..')
$distDir = Join-Path $repoRoot 'dist'
$wxsPath = Join-Path $repoRoot 'installers/windows/usb-tool.wxs'
$intermediateDir = Join-Path $repoRoot 'installers/windows/build'
$iconPath = Join-Path $repoRoot 'build/USBTool.ico'
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $intermediateDir | Out-Null

function Get-MsiVersion([string]$version) {
    if (-not $version) { return '0.0.0' }
    if ($version -notmatch '^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?') {
        return '0.0.0'
    }
    $parts = @($Matches[1], $Matches[2], $Matches[3], $Matches[4]) | ForEach-Object {
        if ($null -eq $_) { '0' } else { $_ }
    }
    while ($parts.Count -gt 4) { $parts = $parts[0..3] }
    while ($parts.Count -lt 3) { $parts += '0' }
    if ($parts.Count -lt 4) { $parts += '0' }
    return $parts -join '.'
}

function Get-UsbVersion {
    $versionFile = Join-Path $repoRoot 'src/usb_tool/_cached_version.txt'
    if (-not (Test-Path $versionFile)) {
        throw "Version cache not found at $versionFile"
    }
    $raw = Get-Content -Path $versionFile -Raw
    if (-not $raw) {
        throw 'Unable to determine usb-tool version from cache'
    }
    return $raw.Trim()
}

function Find-PyInstallerBinary {
    $candidates = @(
        (Join-Path $distDir 'usb-windows.exe')
        (Join-Path $distDir 'usb.exe')
        (Join-Path $distDir 'usb/usb.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    throw "PyInstaller binary not found under $distDir. Build it first."
}

if (-not $SkipPyInstaller) {
    & (Join-Path $repoRoot 'build/build_windows.bat')
}

$usbBinaryPath = Find-PyInstallerBinary
$stagedBinary = Join-Path $distDir 'usb-windows.exe'
if ($usbBinaryPath -ne $stagedBinary) {
    Copy-Item $usbBinaryPath $stagedBinary -Force
}

$version = Get-UsbVersion
$msiVersion = Get-MsiVersion $version
$wixObj = Join-Path $intermediateDir 'usb-tool.wixobj'
if (-not (Test-Path $iconPath)) {
    throw "Product icon not found at $iconPath. Ensure the .ico is present before building the MSI."
}

try {
    $candle = Get-Command candle.exe -ErrorAction Stop
    $light = Get-Command light.exe -ErrorAction Stop
}
catch {
    throw "WiX Toolset binaries (candle.exe/light.exe) not found in PATH. Install WiX 3.14+ and ensure its bin directory is available."
}

$productVersionDefine = "-dProductVersion=$msiVersion"
$binaryDefine = "-dUsbBinary=$stagedBinary"
$iconDefine = "-dProductIcon=$iconPath"

& $candle.Path -ext WixUtilExtension `
    $productVersionDefine `
    $binaryDefine `
    $iconDefine `
    -out $wixObj `
    $wxsPath

$msiPath = Join-Path $distDir "usb-tool-$version-x64.msi"
& $light.Path -ext WixUtilExtension `
    $iconDefine `
    -out $msiPath `
    $wixObj

Write-Host "MSI created at $msiPath"
