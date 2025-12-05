@echo off
setlocal

REM Create a virtual environment
python -m venv .venv
call .venv\Scripts\activate.bat

REM Install dependencies
pip install .
pip install pyinstaller

REM Run PyInstaller
pyinstaller build\\usb_windows.spec

endlocal
