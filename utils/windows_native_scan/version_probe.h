#ifndef WINDOWS_NATIVE_SCAN_VERSION_PROBE_H
#define WINDOWS_NATIVE_SCAN_VERSION_PROBE_H

#include "common.h"

typedef struct {
    bool attempted;
    bool has_payload;
    DWORD open_error;
    DWORD ioctl_error;
    bool interface_attempted;
    bool interface_success;
    double interface_open_ms;
    double interface_ioctl_ms;
    DWORD interface_open_error;
    DWORD interface_ioctl_error;
    bool physical_attempted;
    bool physical_success;
    double physical_open_ms;
    double physical_ioctl_ms;
    DWORD physical_open_error;
    DWORD physical_ioctl_error;
    double parse_ms;
} VersionProbeMeta;

bool probe_device_version(const wchar_t* interface_path,
                          int physical_drive_num,
                          ApricornDevice* device_out,
                          VersionProbeMeta* meta_out);

#endif
