#ifndef WINDOWS_NATIVE_SCAN_DEVNODE_H
#define WINDOWS_NATIVE_SCAN_DEVNODE_H

#include "common.h"

bool query_instance_string(HDEVINFO hdev,
                           SP_DEVINFO_DATA* devinfo,
                           DWORD property,
                           wchar_t* out,
                           DWORD out_cch);
bool get_devnode_reg_dword(DEVINST devinst, ULONG property, DWORD* value_out);
bool parse_rev_from_hardware_ids(DEVINST devinst, char bcd_out[5]);
void populate_driver_info(DEVINST devinst,
                          char provider_out[128],
                          char version_out[64],
                          char inf_out[128]);
bool get_devnode_reg_property(DEVINST devinst,
                              ULONG property,
                              ULONG* reg_type_out,
                              BYTE** buffer_out,
                              ULONG* size_out);
bool derive_bus_number_from_location_paths(DEVINST devinst, int* bus_number_out);

#endif
