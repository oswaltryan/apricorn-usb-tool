#define _CRT_SECURE_NO_WARNINGS
#define _WIN32_WINNT 0x0601

/*
Compatibility translation unit for windows_native_scan.exe.

Canonical modular source tree:
  scripts/windows_native_scan/

Build (MSVC, canonical modular build):
  cl /nologo /O2 /W4 /utf-8 \
    scripts\windows_native_scan\main.c \
    scripts\windows_native_scan\common.c \
    scripts\windows_native_scan\storage.c \
    scripts\windows_native_scan\devnode.c \
    scripts\windows_native_scan\topology.c \
    scripts\windows_native_scan\json_emit.c \
    scripts\windows_native_scan\enumerate.c \
    /link setupapi.lib cfgmgr32.lib

Build (MSVC, compatibility single-file command):
  cl /nologo /O2 /W4 /utf-8 scripts\windows_native_scan.c /link setupapi.lib cfgmgr32.lib

Build (MinGW, canonical modular build):
  gcc -O2 -Wall -Wextra -municode -o windows_native_scan.exe \
    scripts/windows_native_scan/main.c \
    scripts/windows_native_scan/common.c \
    scripts/windows_native_scan/storage.c \
    scripts/windows_native_scan/devnode.c \
    scripts/windows_native_scan/topology.c \
    scripts/windows_native_scan/json_emit.c \
    scripts/windows_native_scan/enumerate.c \
    -lsetupapi -lcfgmgr32

Build (MinGW, compatibility single-file command):
  gcc -O2 -Wall -Wextra -municode -o windows_native_scan.exe scripts/windows_native_scan.c -lsetupapi -lcfgmgr32
*/

#include "windows_native_scan/common.c"
#include "windows_native_scan/storage.c"
#include "windows_native_scan/devnode.c"
#include "windows_native_scan/topology.c"
#include "windows_native_scan/json_emit.c"
#include "windows_native_scan/enumerate.c"
#include "windows_native_scan/main.c"
