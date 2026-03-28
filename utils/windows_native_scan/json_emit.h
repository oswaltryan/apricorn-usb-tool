#ifndef WINDOWS_NATIVE_SCAN_JSON_EMIT_H
#define WINDOWS_NATIVE_SCAN_JSON_EMIT_H

#include "common.h"

int compare_devices_by_drive_num(const void* a, const void* b);
void emit_json(const DeviceVec* devices, const ProfileStats* stats, bool include_profile);

#endif
