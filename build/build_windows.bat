@echo off
setlocal

set "VENV_PATH=.venv_build"
set "SPEC_FILE=build/usb_windows.spec"

echo Checking for virtual environment...
if not exist "%VENV_PATH%" (
    echo Creating virtual environment...
    python -m venv %VENV_PATH%
    if errorlevel 1 (
        echo Failed to create virtual environment.
        exit /b 1
    )
)

echo Activating virtual environment...
call "%VENV_PATH%\Scripts\activate"
if errorlevel 1 (
    echo Failed to activate virtual environment.
    exit /b 1
)

echo Installing dependencies...
pip install pyinstaller libusb pkg_about pywin32
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo Running PyInstaller...
pyinstaller --clean --noconfirm %SPEC_FILE%
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

echo Build complete. The single-file executable is in the 'dist' folder.
endlocal
