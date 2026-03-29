#include "devnode.h"

static const DEVPROPKEY DEVPKEY_DRIVER_PROVIDER_LOCAL = {
    {0xa8b865dd, 0x2e3d, 0x4094, {0xad, 0x97, 0xe5, 0x93, 0xa7, 0x0c, 0x75, 0xd6}},
    9};
static const DEVPROPKEY DEVPKEY_DRIVER_VERSION_LOCAL = {
    {0xa8b865dd, 0x2e3d, 0x4094, {0xad, 0x97, 0xe5, 0x93, 0xa7, 0x0c, 0x75, 0xd6}},
    3};
static const DEVPROPKEY DEVPKEY_DRIVER_INF_PATH_LOCAL = {
    {0xa8b865dd, 0x2e3d, 0x4094, {0xad, 0x97, 0xe5, 0x93, 0xa7, 0x0c, 0x75, 0xd6}},
    5};

static bool get_devnode_property_string(DEVINST devinst,
                                        const DEVPROPKEY* key,
                                        wchar_t* out,
                                        ULONG out_cch) {
    CONFIGRET cr;
    DEVPROPTYPE prop_type = DEVPROP_TYPE_EMPTY;
    ULONG size = out_cch * (ULONG)sizeof(wchar_t);
    out[0] = L'\0';
    cr = CM_Get_DevNode_PropertyW(devinst, key, &prop_type, (PBYTE)out, &size, 0);
    if (cr != CR_SUCCESS || prop_type != DEVPROP_TYPE_STRING || out[0] == L'\0') {
        out[0] = L'\0';
        return false;
    }
    return true;
}

bool query_instance_string(HDEVINFO hdev,
                           SP_DEVINFO_DATA* devinfo,
                           DWORD property,
                           wchar_t* out,
                           DWORD out_cch) {
    DWORD reg_type = 0;
    DWORD required = 0;
    ZeroMemory(out, out_cch * sizeof(wchar_t));
    if (!SetupDiGetDeviceRegistryPropertyW(hdev,
                                           devinfo,
                                           property,
                                           &reg_type,
                                           (PBYTE)out,
                                           out_cch * sizeof(wchar_t),
                                           &required)) {
        return false;
    }
    return true;
}

bool get_devnode_reg_dword(DEVINST devinst, ULONG property, DWORD* value_out) {
    CONFIGRET cr;
    ULONG reg_type = 0;
    ULONG size = sizeof(DWORD);
    DWORD value = 0;
    cr = CM_Get_DevNode_Registry_PropertyW(devinst, property, &reg_type, (PVOID)&value, &size, 0);
    if (cr != CR_SUCCESS) {
        return false;
    }
    if (reg_type != REG_DWORD || size < sizeof(DWORD)) {
        return false;
    }
    *value_out = value;
    return true;
}

bool parse_rev_from_hardware_ids(DEVINST devinst, char bcd_out[5]) {
    CONFIGRET cr;
    ULONG reg_type = 0;
    ULONG size = 0;
    wchar_t* ids = NULL;
    const wchar_t* p = NULL;
    bool matched = false;

    bcd_out[0] = '\0';
    cr = CM_Get_DevNode_Registry_PropertyW(devinst, CM_DRP_HARDWAREID, &reg_type, NULL, &size, 0);
    if (cr != CR_BUFFER_SMALL || size < sizeof(wchar_t)) {
        return false;
    }

    ids = (wchar_t*)malloc(size);
    if (ids == NULL) {
        return false;
    }

    cr = CM_Get_DevNode_Registry_PropertyW(devinst, CM_DRP_HARDWAREID, &reg_type, (PVOID)ids, &size, 0);
    if (cr != CR_SUCCESS || (reg_type != REG_MULTI_SZ && reg_type != REG_SZ)) {
        free(ids);
        return false;
    }

    p = ids;
    while (*p != L'\0') {
        if (parse_hex4_after_token(p, L"REV_", bcd_out)) {
            matched = true;
            break;
        }
        if (reg_type == REG_SZ) {
            break;
        }
        p += wcslen(p) + 1;
    }

    free(ids);
    return matched;
}

void populate_driver_info(DEVINST devinst,
                          char provider_out[128],
                          char version_out[64],
                          char inf_out[128]) {
    wchar_t value_w[512];
    StringCchCopyA(provider_out, 128, "N/A");
    StringCchCopyA(version_out, 64, "N/A");
    StringCchCopyA(inf_out, 128, "N/A");

    if (get_devnode_property_string(devinst, &DEVPKEY_DRIVER_PROVIDER_LOCAL, value_w, ARRAYSIZE(value_w))) {
        wide_to_utf8(value_w, provider_out, 128);
    }
    if (get_devnode_property_string(devinst, &DEVPKEY_DRIVER_VERSION_LOCAL, value_w, ARRAYSIZE(value_w))) {
        wide_to_utf8(value_w, version_out, 64);
    }
    if (get_devnode_property_string(devinst, &DEVPKEY_DRIVER_INF_PATH_LOCAL, value_w, ARRAYSIZE(value_w))) {
        wide_to_utf8(value_w, inf_out, 128);
    }
}

bool get_devnode_reg_property(DEVINST devinst,
                              ULONG property,
                              ULONG* reg_type_out,
                              BYTE** buffer_out,
                              ULONG* size_out) {
    CONFIGRET cr;
    ULONG reg_type = 0;
    ULONG size = 0;
    BYTE* buffer = NULL;

    *buffer_out = NULL;
    *size_out = 0;
    *reg_type_out = 0;

    cr = CM_Get_DevNode_Registry_PropertyW(devinst, property, &reg_type, NULL, &size, 0);
    if (cr != CR_BUFFER_SMALL || size == 0) {
        return false;
    }

    buffer = (BYTE*)malloc(size);
    if (buffer == NULL) {
        return false;
    }
    ZeroMemory(buffer, size);

    cr = CM_Get_DevNode_Registry_PropertyW(devinst, property, &reg_type, (PVOID)buffer, &size, 0);
    if (cr != CR_SUCCESS) {
        free(buffer);
        return false;
    }

    *buffer_out = buffer;
    *size_out = size;
    *reg_type_out = reg_type;
    return true;
}

bool derive_bus_number_from_location_paths(DEVINST devinst, int* bus_number_out) {
    BYTE* buffer = NULL;
    ULONG size = 0;
    ULONG reg_type = 0;
    const wchar_t* path = NULL;
    const wchar_t* p = NULL;
    int usb_hop_count = 0;
    int root_index = 0;
    bool saw_root_digit = false;

    if (!get_devnode_reg_property(devinst, CM_DRP_LOCATION_PATHS, &reg_type, &buffer, &size)) {
        return false;
    }

    if (reg_type != REG_MULTI_SZ && reg_type != REG_SZ) {
        free(buffer);
        return false;
    }

    path = (const wchar_t*)buffer;
    while (path != NULL && path[0] != L'\0') {
        p = wcsstr(path, L"USBROOT(");
        if (p != NULL) {
            const wchar_t* root_digits = p + 8;
            root_index = 0;
            saw_root_digit = false;
            while (*root_digits >= L'0' && *root_digits <= L'9') {
                root_index = (root_index * 10) + (int)(*root_digits - L'0');
                saw_root_digit = true;
                ++root_digits;
            }

            usb_hop_count = 0;
            p += 8;
            while ((p = wcsstr(p, L"USB(")) != NULL) {
                ++usb_hop_count;
                p += 4;
            }

            if (usb_hop_count > 0) {
                *bus_number_out = usb_hop_count + 1;
                free(buffer);
                return true;
            }
            if (saw_root_digit) {
                *bus_number_out = root_index + 1;
                free(buffer);
                return true;
            }
        }
        if (reg_type == REG_SZ) {
            break;
        }
        path += wcslen(path) + 1;
    }

    free(buffer);
    return false;
}
