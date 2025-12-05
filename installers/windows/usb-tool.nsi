; usb-tool.nsi
;
; NSIS script for the usb-tool
;--------------------------------

;--------------------------------
; Includes
!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"
!include "WordFunc.nsh"
!include "TextFunc.nsh"
!include "EnvVarUpdate.nsh"

;--------------------------------
; General

; Name and file
Name "usb-tool"
OutFile "usb-tool-installer.exe"

; Default installation folder
InstallDir "$PROGRAMFILES64\usb-tool"

; Request application privileges for Windows Vista+
RequestExecutionLevel admin

;--------------------------------
; Interface Settings

!define MUI_ABORTWARNING

;--------------------------------
; Pages

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer Sections

Section "Install"
  SetOutPath $INSTDIR

  ; Add your files here
  File "usb.exe"

  ; Add to PATH
  ${EnvVarUpdate} $0 "PATH" "A" "HKLM" "$INSTDIR"

  ; Write the uninstall keys for Windows
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\usb-tool" "DisplayName" "usb-tool"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\usb-tool" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\usb-tool" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\usb-tool" "NoRepair" 1
  WriteUninstaller "uninstall.exe"
SectionEnd

;--------------------------------
; Uninstaller Section

Section "Uninstall"
  ; Remove files
  Delete "$INSTDIR\usb.exe"
  Delete "$INSTDIR\uninstall.exe"

  ; Remove directory
  RMDir "$INSTDIR"

  ; Remove from PATH
  ${EnvVarUpdate} $0 "PATH" "R" "HKLM" "$INSTDIR"

  ; Remove the uninstaller keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\usb-tool"
SectionEnd
