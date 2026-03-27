#define _CRT_SECURE_NO_WARNINGS
#define _WIN32_WINNT 0x0601

/*
Build (MSVC):
  cl /nologo /O2 /W4 /utf-8 scripts\windows_native_scan.c /link setupapi.lib cfgmgr32.lib

Build (MinGW):
  gcc -O2 -Wall -Wextra -municode -o windows_native_scan.exe scripts/windows_native_scan.c -lsetupapi -lcfgmgr32

Run:
  .\windows_native_scan.exe
  .\windows_native_scan.exe --profile
*/

#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strsafe.h>
#include <wchar.h>
#include <wctype.h>
#include <windows.h>
#include <winioctl.h>
#include <cfgmgr32.h>
#include <setupapi.h>
#include <devpkey.h>
#include <usbioctl.h>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "cfgmgr32.lib")

typedef struct {
    int disk_number;
    wchar_t letters[128];
} DriveLetterEntry;

typedef struct {
    char id_vendor[5];
    char id_product[5];
    char bcd_device[5];
    double bcd_usb;
    char serial[128];
    char product[128];
    char device_path[1024];
    char instance_id[1024];
    char driver_transport[16];
    char media_type[32];
    char drive_letter[64];
    char usb_driver_provider[128];
    char usb_driver_version[64];
    char usb_driver_inf[128];
    char disk_driver_provider[128];
    char disk_driver_version[64];
    char disk_driver_inf[128];
    char usb_controller[32];
    int drive_size_gb;
    bool has_drive_size_gb;
    bool oob_mode;
    int physical_drive_num;
    int read_only;
    int bus_number;
    int device_address;
} ApricornDevice;

typedef struct {
    ApricornDevice* items;
    size_t count;
    size_t cap;
} DeviceVec;

typedef struct {
    DriveLetterEntry* items;
    size_t count;
    size_t cap;
} DriveLetterVec;

typedef struct {
    double drive_letter_ms;
    double enumeration_ms;
    double total_ms;
} ProfileStats;

static const char* EXCLUDED_PIDS[] = {"0221", "0211", "0301"};

static const GUID GUID_DEVINTERFACE_DISK_LOCAL = {0x53f56307,
                                                   0xb6bf,
                                                   0x11d0,
                                                   {0x94, 0xf2, 0x00, 0xa0, 0xc9, 0x1e, 0xfb, 0x8b}};
static const GUID GUID_DEVINTERFACE_USB_HUB_LOCAL = {0xf18a0e88,
                                                      0xc30c,
                                                      0x11d0,
                                                      {0x88, 0x15, 0x00, 0xa0, 0xc9, 0x06, 0xbe, 0xd8}};

static const DEVPROPKEY DEVPKEY_DRIVER_PROVIDER_LOCAL = {
    {0xa8b865dd, 0x2e3d, 0x4094, {0xad, 0x97, 0xe5, 0x93, 0xa7, 0x0c, 0x75, 0xd6}},
    9
};
static const DEVPROPKEY DEVPKEY_DRIVER_VERSION_LOCAL = {
    {0xa8b865dd, 0x2e3d, 0x4094, {0xad, 0x97, 0xe5, 0x93, 0xa7, 0x0c, 0x75, 0xd6}},
    3
};
static const DEVPROPKEY DEVPKEY_DRIVER_INF_PATH_LOCAL = {
    {0xa8b865dd, 0x2e3d, 0x4094, {0xad, 0x97, 0xe5, 0x93, 0xa7, 0x0c, 0x75, 0xd6}},
    5
};

typedef struct {
    const char* pid;
    const int* sizes;
    size_t size_count;
} SizeProfile;

static const int PID_0310_SIZES[] = {256, 500, 1000, 2000, 4000, 8000, 16000};
static const int PID_0315_SIZES[] = {
    2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000};
static const int PID_0351_SIZES[] = {128, 256, 500, 1000, 2000, 4000, 8000, 12000, 16000};
static const int PID_1400_SIZES[] = {256, 500, 1000, 2000, 4000, 8000, 16000};
static const int PID_1405_SIZES[] = {240, 480, 1000, 2000, 4000};
static const int PID_1406_SIZES[] = {
    2000, 4000, 6000, 8000, 10000, 12000, 16000, 18000, 20000, 22000, 24000};
static const int PID_1407_SIZES[] = {16, 30, 60, 120, 240, 480, 1000, 2000, 4000};
static const int PID_1408_SIZES[] = {500, 512, 1000, 2000, 4000, 5000, 8000, 16000, 20000};
static const int PID_1409_SIZES[] = {8, 16, 32, 64, 128, 256, 500, 1000, 2000, 4000};
static const int PID_1410_SIZES[] = {4, 8, 16, 32, 64, 128, 256, 512};
static const int PID_1413_SIZES[] = {500, 1000, 2000, 4000};

static const SizeProfile SIZE_PROFILES[] = {
    {"0310", PID_0310_SIZES, ARRAYSIZE(PID_0310_SIZES)},
    {"0315", PID_0315_SIZES, ARRAYSIZE(PID_0315_SIZES)},
    {"0351", PID_0351_SIZES, ARRAYSIZE(PID_0351_SIZES)},
    {"1400", PID_1400_SIZES, ARRAYSIZE(PID_1400_SIZES)},
    {"1405", PID_1405_SIZES, ARRAYSIZE(PID_1405_SIZES)},
    {"1406", PID_1406_SIZES, ARRAYSIZE(PID_1406_SIZES)},
    {"1407", PID_1407_SIZES, ARRAYSIZE(PID_1407_SIZES)},
    {"1408", PID_1408_SIZES, ARRAYSIZE(PID_1408_SIZES)},
    {"1409", PID_1409_SIZES, ARRAYSIZE(PID_1409_SIZES)},
    {"1410", PID_1410_SIZES, ARRAYSIZE(PID_1410_SIZES)},
    {"1413", PID_1413_SIZES, ARRAYSIZE(PID_1413_SIZES)},
};

static double now_ms(void) {
    static LARGE_INTEGER freq = {0};
    LARGE_INTEGER counter = {0};
    if (freq.QuadPart == 0) {
        QueryPerformanceFrequency(&freq);
    }
    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart * 1000.0 / (double)freq.QuadPart;
}

static int abs_int(int value) {
    return value < 0 ? -value : value;
}

static bool lookup_size_profile(const char* pid, const int** out_sizes, size_t* out_count) {
    size_t i = 0;
    for (i = 0; i < ARRAYSIZE(SIZE_PROFILES); ++i) {
        if (_stricmp(pid, SIZE_PROFILES[i].pid) == 0) {
            *out_sizes = SIZE_PROFILES[i].sizes;
            *out_count = SIZE_PROFILES[i].size_count;
            return true;
        }
    }
    *out_sizes = NULL;
    *out_count = 0;
    return false;
}

static int normalize_size_gb(const char* pid, double raw_gib) {
    const int* sizes = NULL;
    size_t count = 0;
    size_t i = 0;
    int target = (int)(raw_gib + 0.5);
    int best = target;
    int best_diff = 0;
    if (target <= 0) {
        return 0;
    }
    if (!lookup_size_profile(pid, &sizes, &count) || count == 0 || sizes == NULL) {
        return target;
    }
    best = sizes[0];
    best_diff = abs_int(sizes[0] - target);
    for (i = 1; i < count; ++i) {
        int diff = abs_int(sizes[i] - target);
        if (diff < best_diff) {
            best = sizes[i];
            best_diff = diff;
        }
    }
    return best;
}

static bool vec_push_device(DeviceVec* vec, const ApricornDevice* item) {
    if (vec->count == vec->cap) {
        size_t next_cap = vec->cap == 0 ? 8 : vec->cap * 2;
        ApricornDevice* next = (ApricornDevice*)realloc(vec->items, next_cap * sizeof(*next));
        if (next == NULL) {
            return false;
        }
        vec->items = next;
        vec->cap = next_cap;
    }
    vec->items[vec->count++] = *item;
    return true;
}

static bool vec_push_drive_letter(DriveLetterVec* vec, const DriveLetterEntry* item) {
    if (vec->count == vec->cap) {
        size_t next_cap = vec->cap == 0 ? 16 : vec->cap * 2;
        DriveLetterEntry* next =
            (DriveLetterEntry*)realloc(vec->items, next_cap * sizeof(*next));
        if (next == NULL) {
            return false;
        }
        vec->items = next;
        vec->cap = next_cap;
    }
    vec->items[vec->count++] = *item;
    return true;
}

static bool is_excluded_pid(const char* pid) {
    size_t i = 0;
    for (i = 0; i < sizeof(EXCLUDED_PIDS) / sizeof(EXCLUDED_PIDS[0]); ++i) {
        if (_stricmp(pid, EXCLUDED_PIDS[i]) == 0) {
            return true;
        }
    }
    return false;
}

static void wide_to_utf8(const wchar_t* ws, char* out, size_t out_cap) {
    int bytes = 0;
    if (out_cap == 0) {
        return;
    }
    out[0] = '\0';
    if (ws == NULL || ws[0] == L'\0') {
        return;
    }
    bytes = WideCharToMultiByte(CP_UTF8, 0, ws, -1, out, (int)out_cap, NULL, NULL);
    if (bytes <= 0) {
        out[0] = '\0';
    }
}

static void uppercase_hex4(char* value) {
    size_t i = 0;
    for (i = 0; i < 4 && value[i] != '\0'; ++i) {
        value[i] = (char)toupper((unsigned char)value[i]);
    }
}

static bool parse_hex4_after_token(const wchar_t* text, const wchar_t* token, char out[5]) {
    const wchar_t* p = NULL;
    int i = 0;
    if (text == NULL || token == NULL) {
        return false;
    }
    p = wcsstr(text, token);
    if (p == NULL) {
        return false;
    }
    p += wcslen(token);
    for (i = 0; i < 4; ++i) {
        wchar_t c = p[i];
        if (!iswxdigit(c)) {
            return false;
        }
        out[i] = (char)tolower((unsigned char)c);
    }
    out[4] = '\0';
    uppercase_hex4(out);
    return true;
}

static void extract_serial_segment(const wchar_t* instance_id, char out[128]) {
    const wchar_t* last = NULL;
    char tmp[256];
    char* amp = NULL;
    out[0] = '\0';
    if (instance_id == NULL) {
        return;
    }
    last = wcsrchr(instance_id, L'\\');
    if (last == NULL || last[1] == L'\0') {
        return;
    }
    wide_to_utf8(last + 1, tmp, sizeof(tmp));
    amp = strchr(tmp, '&');
    if (amp != NULL) {
        *amp = '\0';
    }
    StringCchCopyA(out, 128, tmp);
}

static void extract_product_hint(const wchar_t* instance_id, char out[128]) {
    const wchar_t* p = NULL;
    wchar_t token[128];
    size_t i = 0;
    out[0] = '\0';
    if (instance_id == NULL) {
        return;
    }
    p = wcsstr(instance_id, L"PROD_");
    if (p == NULL) {
        return;
    }
    p += 5;
    while (*p != L'\0' && *p != L'&' && *p != L'#' && i + 1 < sizeof(token) / sizeof(token[0])) {
        token[i++] = (*p == L'_') ? L' ' : *p;
        ++p;
    }
    token[i] = L'\0';
    wide_to_utf8(token, out, 128);
}

static bool get_disk_number_from_path(const wchar_t* path, int* disk_number_out) {
    HANDLE h = INVALID_HANDLE_VALUE;
    STORAGE_DEVICE_NUMBER number;
    DWORD out_bytes = 0;
    BOOL ok = FALSE;

    *disk_number_out = -1;
    h = CreateFileW(path,
                    0,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    NULL,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    NULL);
    if (h == INVALID_HANDLE_VALUE) {
        return false;
    }

    ZeroMemory(&number, sizeof(number));
    ok = DeviceIoControl(h,
                         IOCTL_STORAGE_GET_DEVICE_NUMBER,
                         NULL,
                         0,
                         &number,
                         (DWORD)sizeof(number),
                         &out_bytes,
                         NULL);
    CloseHandle(h);
    if (!ok) {
        return false;
    }
    *disk_number_out = (int)number.DeviceNumber;
    return true;
}

static void append_drive_letter_token(wchar_t* letters, size_t cap, const wchar_t* token) {
    if (letters[0] == L'\0') {
        StringCchCopyW(letters, cap, token);
        return;
    }
    if (wcsstr(letters, token) != NULL) {
        return;
    }
    StringCchCatW(letters, cap, L", ");
    StringCchCatW(letters, cap, token);
}

static void collect_drive_letter_map(DriveLetterVec* map) {
    DWORD mask = GetLogicalDrives();
    int i = 0;
    for (i = 0; i < 26; ++i) {
        wchar_t drive_letter;
        wchar_t root[4];
        wchar_t open_path[8];
        HANDLE h = INVALID_HANDLE_VALUE;
        STORAGE_DEVICE_NUMBER number;
        DWORD out_bytes = 0;
        size_t j = 0;
        bool inserted = false;
        DWORD idx = 0;

        if ((mask & (1u << i)) == 0) {
            continue;
        }

        drive_letter = (wchar_t)(L'A' + i);
        root[0] = drive_letter;
        root[1] = L':';
        root[2] = L'\\';
        root[3] = L'\0';
        if (GetDriveTypeW(root) != DRIVE_FIXED && GetDriveTypeW(root) != DRIVE_REMOVABLE) {
            continue;
        }

        StringCchPrintfW(open_path, ARRAYSIZE(open_path), L"\\\\.\\%c:", drive_letter);
        h = CreateFileW(open_path,
                        0,
                        FILE_SHARE_READ | FILE_SHARE_WRITE,
                        NULL,
                        OPEN_EXISTING,
                        FILE_ATTRIBUTE_NORMAL,
                        NULL);
        if (h == INVALID_HANDLE_VALUE) {
            continue;
        }

        ZeroMemory(&number, sizeof(number));
        if (!DeviceIoControl(h,
                             IOCTL_STORAGE_GET_DEVICE_NUMBER,
                             NULL,
                             0,
                             &number,
                             (DWORD)sizeof(number),
                             &out_bytes,
                             NULL)) {
            CloseHandle(h);
            continue;
        }
        CloseHandle(h);

        for (j = 0; j < map->count; ++j) {
            if (map->items[j].disk_number == (int)number.DeviceNumber) {
                idx = (DWORD)j;
                inserted = true;
                break;
            }
        }
        if (!inserted) {
            DriveLetterEntry entry;
            entry.disk_number = (int)number.DeviceNumber;
            entry.letters[0] = L'\0';
            if (!vec_push_drive_letter(map, &entry)) {
                break;
            }
            idx = (DWORD)(map->count - 1);
        }

        {
            wchar_t token[3];
            token[0] = drive_letter;
            token[1] = L':';
            token[2] = L'\0';
            append_drive_letter_token(map->items[idx].letters,
                                      sizeof(map->items[idx].letters) / sizeof(map->items[idx].letters[0]),
                                      token);
        }
    }
}

static const wchar_t* lookup_drive_letters(const DriveLetterVec* map, int disk_number) {
    size_t i = 0;
    for (i = 0; i < map->count; ++i) {
        if (map->items[i].disk_number == disk_number) {
            if (map->items[i].letters[0] != L'\0') {
                return map->items[i].letters;
            }
            break;
        }
    }
    return L"Not Formatted";
}

static void classify_transport(const wchar_t* instance_id, const wchar_t* service, char out[16]) {
    out[0] = '\0';
    if (instance_id != NULL) {
        if (_wcsnicmp(instance_id, L"SCSI\\", 5) == 0) {
            StringCchCopyA(out, 16, "UAS");
            return;
        }
        if (_wcsnicmp(instance_id, L"USBSTOR\\", 8) == 0) {
            StringCchCopyA(out, 16, "BOT");
            return;
        }
    }
    if (service != NULL) {
        if (_wcsicmp(service, L"uaspstor") == 0 || _wcsicmp(service, L"uaspstor.sys") == 0) {
            StringCchCopyA(out, 16, "UAS");
            return;
        }
        if (_wcsicmp(service, L"USBSTOR") == 0 || _wcsicmp(service, L"usbstor.sys") == 0) {
            StringCchCopyA(out, 16, "BOT");
            return;
        }
    }
    StringCchCopyA(out, 16, "Unknown");
}

static bool get_physical_drive_metrics(int disk_number,
                                       double* size_gb_raw_out,
                                       bool* oob_mode_out,
                                       int* read_only_out,
                                       double* bcd_usb_out) {
    wchar_t path[64];
    HANDLE h = INVALID_HANDLE_VALUE;
    GET_LENGTH_INFORMATION len_info;
    STORAGE_PROPERTY_QUERY prop_query;
    BYTE prop_buf[1024];
    DWORD out_bytes = 0;
    BOOL len_ok = FALSE;
    BOOL writable_ok = FALSE;
    unsigned long long bytes = 0ULL;
    double gib = 0.0;

    *read_only_out = 0;
    *size_gb_raw_out = 0.0;
    *oob_mode_out = false;
    *bcd_usb_out = 0.0;
    StringCchPrintfW(path, 64, L"\\\\.\\PhysicalDrive%d", disk_number);
    h = CreateFileW(path,
                    0,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    NULL,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    NULL);
    if (h == INVALID_HANDLE_VALUE) {
        return false;
    }

    ZeroMemory(&prop_query, sizeof(prop_query));
    prop_query.PropertyId = StorageAdapterProperty;
    prop_query.QueryType = PropertyStandardQuery;
    ZeroMemory(prop_buf, sizeof(prop_buf));
    out_bytes = 0;
    if (DeviceIoControl(h,
                        IOCTL_STORAGE_QUERY_PROPERTY,
                        &prop_query,
                        (DWORD)sizeof(prop_query),
                        prop_buf,
                        (DWORD)sizeof(prop_buf),
                        &out_bytes,
                        NULL) &&
        out_bytes >= sizeof(STORAGE_ADAPTER_DESCRIPTOR)) {
        const STORAGE_ADAPTER_DESCRIPTOR* desc = (const STORAGE_ADAPTER_DESCRIPTOR*)prop_buf;
        if (desc->BusType == BusTypeUsb && desc->BusMajorVersion > 0) {
            *bcd_usb_out = (double)desc->BusMajorVersion + ((double)desc->BusMinorVersion / 10.0);
        }
    }

    ZeroMemory(&len_info, sizeof(len_info));
    len_ok = DeviceIoControl(h,
                             IOCTL_DISK_GET_LENGTH_INFO,
                             NULL,
                             0,
                             &len_info,
                             (DWORD)sizeof(len_info),
                             &out_bytes,
                             NULL);
    if (!len_ok) {
        bytes = 0ULL;
    } else {
        bytes = (unsigned long long)len_info.Length.QuadPart;
    }

    out_bytes = 0;
    writable_ok = DeviceIoControl(h, IOCTL_DISK_IS_WRITABLE, NULL, 0, NULL, 0, &out_bytes, NULL);
    if (!writable_ok && GetLastError() == ERROR_WRITE_PROTECT) {
        *read_only_out = 1;
    }
    CloseHandle(h);

    if (len_ok && bytes == 0ULL) {
        *oob_mode_out = true;
        return true;
    }

    gib = (double)bytes / (1024.0 * 1024.0 * 1024.0);
    *size_gb_raw_out = gib;
    return true;
}

static bool query_instance_string(HDEVINFO hdev, SP_DEVINFO_DATA* devinfo, DWORD property, wchar_t* out, DWORD out_cch) {
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

static bool get_devnode_reg_dword(DEVINST devinst, ULONG property, DWORD* value_out) {
    CONFIGRET cr;
    ULONG reg_type = 0;
    ULONG size = sizeof(DWORD);
    DWORD value = 0;
    cr = CM_Get_DevNode_Registry_PropertyW(
        devinst, property, &reg_type, (PVOID)&value, &size, 0);
    if (cr != CR_SUCCESS) {
        return false;
    }
    if (reg_type != REG_DWORD || size < sizeof(DWORD)) {
        return false;
    }
    *value_out = value;
    return true;
}

static bool parse_rev_from_hardware_ids(DEVINST devinst, char bcd_out[5]) {
    CONFIGRET cr;
    ULONG reg_type = 0;
    ULONG size = 0;
    wchar_t* ids = NULL;
    const wchar_t* p = NULL;
    bool matched = false;

    bcd_out[0] = '\0';
    cr = CM_Get_DevNode_Registry_PropertyW(
        devinst, CM_DRP_HARDWAREID, &reg_type, NULL, &size, 0);
    if (cr != CR_BUFFER_SMALL || size < sizeof(wchar_t)) {
        return false;
    }

    ids = (wchar_t*)malloc(size);
    if (ids == NULL) {
        return false;
    }

    cr = CM_Get_DevNode_Registry_PropertyW(
        devinst, CM_DRP_HARDWAREID, &reg_type, (PVOID)ids, &size, 0);
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

static bool get_devnode_property_string(
    DEVINST devinst,
    const DEVPROPKEY* key,
    wchar_t* out,
    ULONG out_cch
) {
    CONFIGRET cr;
    DEVPROPTYPE prop_type = DEVPROP_TYPE_EMPTY;
    ULONG size = out_cch * (ULONG)sizeof(wchar_t);
    out[0] = L'\0';
    cr = CM_Get_DevNode_PropertyW(
        devinst, key, &prop_type, (PBYTE)out, &size, 0);
    if (cr != CR_SUCCESS || prop_type != DEVPROP_TYPE_STRING || out[0] == L'\0') {
        out[0] = L'\0';
        return false;
    }
    return true;
}

static void populate_driver_info(
    DEVINST devinst,
    char provider_out[128],
    char version_out[64],
    char inf_out[128]
) {
    wchar_t value_w[512];
    StringCchCopyA(provider_out, 128, "N/A");
    StringCchCopyA(version_out, 64, "N/A");
    StringCchCopyA(inf_out, 128, "N/A");

    if (get_devnode_property_string(
            devinst, &DEVPKEY_DRIVER_PROVIDER_LOCAL, value_w, ARRAYSIZE(value_w))) {
        wide_to_utf8(value_w, provider_out, 128);
    }
    if (get_devnode_property_string(
            devinst, &DEVPKEY_DRIVER_VERSION_LOCAL, value_w, ARRAYSIZE(value_w))) {
        wide_to_utf8(value_w, version_out, 64);
    }
    if (get_devnode_property_string(
            devinst, &DEVPKEY_DRIVER_INF_PATH_LOCAL, value_w, ARRAYSIZE(value_w))) {
        wide_to_utf8(value_w, inf_out, 128);
    }
}

static bool get_size_from_drive_letters(const char* letters_csv, double* size_gib_out) {
    const char* p = letters_csv;
    unsigned long long best_bytes = 0ULL;
    bool found = false;

    while (*p != '\0') {
        char root[] = {'\0', ':', '\\', '\0'};
        ULARGE_INTEGER total_bytes;

        while (*p == ' ' || *p == ',') {
            ++p;
        }
        if (*p == '\0') {
            break;
        }

        if (!isalpha((unsigned char)p[0]) || p[1] != ':') {
            while (*p != '\0' && *p != ',') {
                ++p;
            }
            continue;
        }

        root[0] = (char)toupper((unsigned char)p[0]);
        ZeroMemory(&total_bytes, sizeof(total_bytes));
        if (GetDiskFreeSpaceExA(root, NULL, &total_bytes, NULL) && total_bytes.QuadPart > 0ULL) {
            if (total_bytes.QuadPart > best_bytes) {
                best_bytes = total_bytes.QuadPart;
            }
            found = true;
        }

        while (*p != '\0' && *p != ',') {
            ++p;
        }
    }

    if (!found || best_bytes == 0ULL) {
        return false;
    }

    *size_gib_out = (double)best_bytes / (1024.0 * 1024.0 * 1024.0);
    return true;
}

static bool get_devnode_reg_property(
    DEVINST devinst, ULONG property, ULONG* reg_type_out, BYTE** buffer_out, ULONG* size_out) {
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

    cr = CM_Get_DevNode_Registry_PropertyW(
        devinst, property, &reg_type, (PVOID)buffer, &size, 0);
    if (cr != CR_SUCCESS) {
        free(buffer);
        return false;
    }

    *buffer_out = buffer;
    *size_out = size;
    *reg_type_out = reg_type;
    return true;
}

static bool parse_port_from_location_info(const wchar_t* location_info, int* port_out) {
    const wchar_t* p;
    int port = 0;
    if (location_info == NULL) {
        return false;
    }
    p = wcsstr(location_info, L"Port_#");
    if (p == NULL) {
        return false;
    }
    p += 6;
    while (*p >= L'0' && *p <= L'9') {
        port = (port * 10) + (int)(*p - L'0');
        ++p;
    }
    if (port <= 0) {
        return false;
    }
    *port_out = port;
    return true;
}

static bool derive_bus_number_from_location_paths(DEVINST devinst, int* bus_number_out) {
    BYTE* buffer = NULL;
    ULONG size = 0;
    ULONG reg_type = 0;
    const wchar_t* path = NULL;
    const wchar_t* p = NULL;
    int usb_hop_count = 0;
    int root_index = 0;
    bool saw_root_digit = false;

    if (!get_devnode_reg_property(
            devinst, CM_DRP_LOCATION_PATHS, &reg_type, &buffer, &size)) {
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

static bool get_hub_interface_path_for_devinst(
    DEVINST hub_devinst, wchar_t* path_out, DWORD path_out_cch) {
    HDEVINFO hubs;
    SP_DEVICE_INTERFACE_DATA if_data;
    DWORD index = 0;
    wchar_t wanted_id[1024];

    if (CM_Get_Device_IDW(hub_devinst, wanted_id, ARRAYSIZE(wanted_id), 0) != CR_SUCCESS) {
        return false;
    }

    hubs = SetupDiGetClassDevsW(
        &GUID_DEVINTERFACE_USB_HUB_LOCAL, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (hubs == INVALID_HANDLE_VALUE) {
        return false;
    }

    ZeroMemory(&if_data, sizeof(if_data));
    if_data.cbSize = sizeof(if_data);

    while (SetupDiEnumDeviceInterfaces(hubs, NULL, &GUID_DEVINTERFACE_USB_HUB_LOCAL, index, &if_data)) {
        DWORD required = 0;
        PSP_DEVICE_INTERFACE_DETAIL_DATA_W detail = NULL;
        SP_DEVINFO_DATA devinfo;
        wchar_t instance_id[1024];
        BOOL ok = FALSE;

        ZeroMemory(&devinfo, sizeof(devinfo));
        devinfo.cbSize = sizeof(devinfo);
        SetupDiGetDeviceInterfaceDetailW(hubs, &if_data, NULL, 0, &required, &devinfo);
        detail = (PSP_DEVICE_INTERFACE_DETAIL_DATA_W)malloc(required);
        if (detail == NULL) {
            break;
        }
        detail->cbSize = sizeof(*detail);
        ok = SetupDiGetDeviceInterfaceDetailW(hubs, &if_data, detail, required, NULL, &devinfo);
        if (!ok) {
            free(detail);
            ++index;
            continue;
        }

        ZeroMemory(instance_id, sizeof(instance_id));
        if (SetupDiGetDeviceInstanceIdW(
                hubs, &devinfo, instance_id, ARRAYSIZE(instance_id), NULL) &&
            _wcsicmp(instance_id, wanted_id) == 0) {
            StringCchCopyW(path_out, path_out_cch, detail->DevicePath);
            free(detail);
            SetupDiDestroyDeviceInfoList(hubs);
            return true;
        }

        free(detail);
        ++index;
    }

    SetupDiDestroyDeviceInfoList(hubs);
    return false;
}

static double usb_bcd_to_float(USHORT bcd_usb) {
    int major = (bcd_usb >> 8) & 0xFF;
    int minor = (bcd_usb >> 4) & 0x0F;
    return (double)major + ((double)minor / 10.0);
}

static bool query_connection_metrics_from_parent_hub(
    DEVINST usb_devinst,
    const char* expected_vid,
    const char* expected_pid,
    double* bcd_usb_out,
    int* device_address_out,
    char bcd_device_out[5]) {
    DEVINST parent = 0;
    BYTE* location_buf = NULL;
    ULONG location_type = 0;
    ULONG location_size = 0;
    wchar_t hub_path[1024];
    HANDLE h_hub = INVALID_HANDLE_VALUE;
    USB_NODE_CONNECTION_INFORMATION_EX conn;
    DWORD out_bytes = 0;
    int port = 0;
    bool ok = false;
    char vid[5];
    char pid[5];
    char bcd[5];

    if (CM_Get_Parent(&parent, usb_devinst, 0) != CR_SUCCESS) {
        return false;
    }
    if (!get_devnode_reg_property(
            usb_devinst,
            CM_DRP_LOCATION_INFORMATION,
            &location_type,
            &location_buf,
            &location_size)) {
        return false;
    }
    if (location_type != REG_SZ && location_type != REG_MULTI_SZ) {
        free(location_buf);
        return false;
    }
    if (!parse_port_from_location_info((const wchar_t*)location_buf, &port)) {
        free(location_buf);
        return false;
    }
    free(location_buf);

    if (!get_hub_interface_path_for_devinst(parent, hub_path, ARRAYSIZE(hub_path))) {
        return false;
    }

    h_hub = CreateFileW(
        hub_path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h_hub == INVALID_HANDLE_VALUE) {
        h_hub = CreateFileW(
            hub_path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    }
    if (h_hub == INVALID_HANDLE_VALUE) {
        return false;
    }

    ZeroMemory(&conn, sizeof(conn));
    conn.ConnectionIndex = (ULONG)port;
    if (!DeviceIoControl(h_hub,
                         IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX,
                         &conn,
                         (DWORD)sizeof(conn),
                         &conn,
                         (DWORD)sizeof(conn),
                         &out_bytes,
                         NULL)) {
        CloseHandle(h_hub);
        return false;
    }
    CloseHandle(h_hub);

    StringCchPrintfA(vid, ARRAYSIZE(vid), "%04X", conn.DeviceDescriptor.idVendor);
    StringCchPrintfA(pid, ARRAYSIZE(pid), "%04X", conn.DeviceDescriptor.idProduct);
    StringCchPrintfA(bcd, ARRAYSIZE(bcd), "%04X", conn.DeviceDescriptor.bcdDevice);
    if (_stricmp(expected_vid, vid) != 0 || _stricmp(expected_pid, pid) != 0) {
        return false;
    }

    *bcd_usb_out = usb_bcd_to_float(conn.DeviceDescriptor.bcdUSB);
    *device_address_out = (int)conn.DeviceAddress;
    if (bcd_device_out != NULL) {
        StringCchCopyA(bcd_device_out, 5, bcd);
    }
    ok = true;
    return ok;
}

static void classify_usb_controller(DEVINST usb_devinst, char out[32]) {
    DEVINST cur = usb_devinst;
    int depth = 0;
    wchar_t instance_id[1024];
    StringCchCopyA(out, 32, "N/A");
    for (depth = 0; depth < 20; ++depth) {
        DEVINST parent = 0;
        if (CM_Get_Device_IDW(cur, instance_id, ARRAYSIZE(instance_id), 0) != CR_SUCCESS) {
            break;
        }
        if (wcsstr(instance_id, L"PCI\\VEN_8086") != NULL) {
            StringCchCopyA(out, 32, "Intel");
            return;
        }
        if (wcsstr(instance_id, L"PCI\\VEN_") != NULL) {
            StringCchCopyA(out, 32, "ASMedia");
            return;
        }
        if (CM_Get_Parent(&parent, cur, 0) != CR_SUCCESS) {
            break;
        }
        cur = parent;
    }
}

static bool find_usb_identity(DEVINST start_devinst,
                              char vid_out[5],
                              char pid_out[5],
                              char bcd_out[5],
                              char serial_out[128],
                              DEVINST* usb_devinst_out) {
    DEVINST cur = start_devinst;
    int depth = 0;
    wchar_t instance_id[1024];

    vid_out[0] = '\0';
    pid_out[0] = '\0';
    bcd_out[0] = '\0';
    serial_out[0] = '\0';
    if (usb_devinst_out != NULL) {
        *usb_devinst_out = 0;
    }

    for (depth = 0; depth < 10; ++depth) {
        CONFIGRET cr = CM_Get_Device_IDW(cur, instance_id, ARRAYSIZE(instance_id), 0);
        DEVINST parent = 0;
        if (cr != CR_SUCCESS) {
            break;
        }

        if (serial_out[0] == '\0') {
            extract_serial_segment(instance_id, serial_out);
        }
        if (parse_hex4_after_token(instance_id, L"VID_", vid_out) &&
            parse_hex4_after_token(instance_id, L"PID_", pid_out)) {
            if (!parse_hex4_after_token(instance_id, L"REV_", bcd_out)) {
                parse_rev_from_hardware_ids(cur, bcd_out);
            }
            if (bcd_out[0] == '\0') {
                StringCchCopyA(bcd_out, 5, "0000");
            }
            if (usb_devinst_out != NULL) {
                *usb_devinst_out = cur;
            }
            return _stricmp(vid_out, "0984") == 0;
        }

        cr = CM_Get_Parent(&parent, cur, 0);
        if (cr != CR_SUCCESS) {
            break;
        }
        cur = parent;
    }

    return false;
}

static int compare_devices_by_drive_num(const void* a, const void* b) {
    const ApricornDevice* da = (const ApricornDevice*)a;
    const ApricornDevice* db = (const ApricornDevice*)b;
    int a_num = da->physical_drive_num >= 0 ? da->physical_drive_num : INT32_MAX;
    int b_num = db->physical_drive_num >= 0 ? db->physical_drive_num : INT32_MAX;
    if (a_num < b_num) {
        return -1;
    }
    if (a_num > b_num) {
        return 1;
    }
    return _stricmp(da->serial, db->serial);
}

static void json_print_escaped(const char* s) {
    const unsigned char* p = (const unsigned char*)s;
    putchar('"');
    while (*p != '\0') {
        switch (*p) {
            case '"':
                fputs("\\\"", stdout);
                break;
            case '\\':
                fputs("\\\\", stdout);
                break;
            case '\b':
                fputs("\\b", stdout);
                break;
            case '\f':
                fputs("\\f", stdout);
                break;
            case '\n':
                fputs("\\n", stdout);
                break;
            case '\r':
                fputs("\\r", stdout);
                break;
            case '\t':
                fputs("\\t", stdout);
                break;
            default:
                if (*p < 0x20) {
                    fprintf(stdout, "\\u%04x", *p);
                } else {
                    putchar(*p);
                }
        }
        ++p;
    }
    putchar('"');
}

static void emit_device_payload(const ApricornDevice* d) {
    fputs("        \"bcdUSB\": ", stdout);
    fprintf(stdout, "%.1f,\n", d->bcd_usb);
    fputs("        \"idVendor\": ", stdout);
    json_print_escaped(d->id_vendor);
    fputs(",\n        \"idProduct\": ", stdout);
    json_print_escaped(d->id_product);
    fputs(",\n        \"bcdDevice\": ", stdout);
    json_print_escaped(d->bcd_device);
    fputs(",\n        \"iManufacturer\": \"Apricorn\",\n        \"iProduct\": ", stdout);
    json_print_escaped(d->product);
    fputs(",\n        \"iSerial\": ", stdout);
    json_print_escaped(d->serial);
    fputs(",\n        \"driverTransport\": ", stdout);
    json_print_escaped(d->driver_transport);
    fputs(",\n        \"driveSizeGB\": ", stdout);
    if (d->oob_mode) {
        json_print_escaped("N/A (OOB Mode)");
    } else if (d->has_drive_size_gb) {
        fprintf(stdout, "%d", d->drive_size_gb);
    } else {
        json_print_escaped("N/A");
    }
    fputs(",\n        \"mediaType\": ", stdout);
    json_print_escaped(d->media_type);
    fputs(",\n        \"usbDriverProvider\": ", stdout);
    json_print_escaped(d->usb_driver_provider);
    fputs(",\n        \"usbDriverVersion\": ", stdout);
    json_print_escaped(d->usb_driver_version);
    fputs(",\n        \"usbDriverInf\": ", stdout);
    json_print_escaped(d->usb_driver_inf);
    fputs(",\n        \"diskDriverProvider\": ", stdout);
    json_print_escaped(d->disk_driver_provider);
    fputs(",\n        \"diskDriverVersion\": ", stdout);
    json_print_escaped(d->disk_driver_version);
    fputs(",\n        \"diskDriverInf\": ", stdout);
    json_print_escaped(d->disk_driver_inf);
    fputs(",\n        \"usbController\": ", stdout);
    json_print_escaped(d->usb_controller);
    fputs(",\n        \"busNumber\": ", stdout);
    fprintf(stdout, "%d", d->bus_number);
    fputs(",\n        \"deviceAddress\": ", stdout);
    fprintf(stdout, "%d", d->device_address);
    fputs(",\n        \"physicalDriveNum\": ", stdout);
    fprintf(stdout, "%d", d->physical_drive_num);
    fputs(",\n        \"driveLetter\": ", stdout);
    json_print_escaped(d->drive_letter);
    fputs(",\n        \"readOnly\": ", stdout);
    fputs(d->read_only ? "true" : "false", stdout);
    if (d->oob_mode) {
        fputs(",\n        \"scbPartNumber\": \"N/A\"", stdout);
        fputs(",\n        \"hardwareVersion\": \"N/A\"", stdout);
        fputs(",\n        \"modelID\": \"N/A\"", stdout);
        fputs(",\n        \"mcuFW\": \"N/A\"", stdout);
    }
}

static void emit_json(const DeviceVec* devices, const ProfileStats* stats, bool include_profile) {
    size_t i = 0;
    fputs("{\n", stdout);
    if (devices->count == 0) {
        fputs("  \"devices\": []", stdout);
    } else {
        fputs("  \"devices\": [\n", stdout);
        fputs("    {\n", stdout);
        for (i = 0; i < devices->count; ++i) {
            const ApricornDevice* d = &devices->items[i];
            fputs("      \"", stdout);
            fprintf(stdout, "%u", (unsigned)(i + 1));
            fputs("\": {\n", stdout);
            emit_device_payload(d);
            fputs("\n      }", stdout);
            if (i + 1 < devices->count) {
                fputs(",", stdout);
            }
            fputs("\n", stdout);
        }
        fputs("    }\n", stdout);
        fputs("  ]", stdout);
    }
    if (include_profile) {
        fputs(",\n", stdout);
        fputs("  \"profile\": {\n", stdout);
        fprintf(stdout, "    \"driveLettersMs\": %.2f,\n", stats->drive_letter_ms);
        fprintf(stdout, "    \"enumerationMs\": %.2f,\n", stats->enumeration_ms);
        fprintf(stdout, "    \"totalMs\": %.2f\n", stats->total_ms);
        fputs("  }\n", stdout);
    } else {
        fputs("\n", stdout);
    }
    fputs("}\n", stdout);
}

static bool enumerate_apricorn_devices(DeviceVec* devices, ProfileStats* stats) {
    HDEVINFO hdev = INVALID_HANDLE_VALUE;
    SP_DEVICE_INTERFACE_DATA if_data;
    DWORD index = 0;
    double enum_start = now_ms();
    DriveLetterVec drive_map = {0};
    double letter_start = 0.0;
    bool success = true;

    letter_start = now_ms();
    collect_drive_letter_map(&drive_map);
    stats->drive_letter_ms = now_ms() - letter_start;

    hdev = SetupDiGetClassDevsW(&GUID_DEVINTERFACE_DISK_LOCAL,
                                NULL,
                                NULL,
                                DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (hdev == INVALID_HANDLE_VALUE) {
        free(drive_map.items);
        return false;
    }

    ZeroMemory(&if_data, sizeof(if_data));
    if_data.cbSize = sizeof(if_data);

    while (SetupDiEnumDeviceInterfaces(hdev, NULL, &GUID_DEVINTERFACE_DISK_LOCAL, index, &if_data)) {
        DWORD required = 0;
        PSP_DEVICE_INTERFACE_DETAIL_DATA_W detail = NULL;
        SP_DEVINFO_DATA dev_info;
        BOOL detail_ok = FALSE;
        wchar_t instance_id_w[1024];
        wchar_t desc_w[512];
        wchar_t service_w[256];
        char vid[5];
        char pid[5];
        char bcd[5];
        char serial[128];
        DEVINST usb_devinst = 0;
        int disk_number = -1;
        ApricornDevice out;
        const wchar_t* letters_w = NULL;

        dev_info.cbSize = sizeof(dev_info);
        SetupDiGetDeviceInterfaceDetailW(
            hdev, &if_data, NULL, 0, &required, &dev_info);

        detail = (PSP_DEVICE_INTERFACE_DETAIL_DATA_W)malloc(required);
        if (detail == NULL) {
            success = false;
            break;
        }
        detail->cbSize = sizeof(*detail);
        detail_ok = SetupDiGetDeviceInterfaceDetailW(
            hdev, &if_data, detail, required, NULL, &dev_info);
        if (!detail_ok) {
            free(detail);
            ++index;
            continue;
        }

        ZeroMemory(instance_id_w, sizeof(instance_id_w));
        if (!SetupDiGetDeviceInstanceIdW(hdev, &dev_info, instance_id_w, ARRAYSIZE(instance_id_w), NULL)) {
            free(detail);
            ++index;
            continue;
        }

        if (!find_usb_identity(dev_info.DevInst, vid, pid, bcd, serial, &usb_devinst)) {
            free(detail);
            ++index;
            continue;
        }
        if (_stricmp(vid, "0984") != 0 || is_excluded_pid(pid)) {
            free(detail);
            ++index;
            continue;
        }

        ZeroMemory(&out, sizeof(out));
        StringCchCopyA(out.id_vendor, ARRAYSIZE(out.id_vendor), vid);
        StringCchCopyA(out.id_product, ARRAYSIZE(out.id_product), pid);
        StringCchCopyA(out.bcd_device, ARRAYSIZE(out.bcd_device), bcd[0] ? bcd : "0000");
        StringCchCopyA(out.serial, ARRAYSIZE(out.serial), serial);
        StringCchCopyA(out.media_type, ARRAYSIZE(out.media_type), "Basic Disk");
        StringCchCopyA(out.usb_driver_provider, ARRAYSIZE(out.usb_driver_provider), "N/A");
        StringCchCopyA(out.usb_driver_version, ARRAYSIZE(out.usb_driver_version), "N/A");
        StringCchCopyA(out.usb_driver_inf, ARRAYSIZE(out.usb_driver_inf), "N/A");
        StringCchCopyA(out.disk_driver_provider, ARRAYSIZE(out.disk_driver_provider), "N/A");
        StringCchCopyA(out.disk_driver_version, ARRAYSIZE(out.disk_driver_version), "N/A");
        StringCchCopyA(out.disk_driver_inf, ARRAYSIZE(out.disk_driver_inf), "N/A");
        StringCchCopyA(out.usb_controller, ARRAYSIZE(out.usb_controller), "N/A");
        out.bcd_usb = 0.0;
        out.bus_number = -1;
        out.device_address = -1;
        out.drive_size_gb = 0;
        out.has_drive_size_gb = false;
        out.oob_mode = false;
        wide_to_utf8(detail->DevicePath, out.device_path, ARRAYSIZE(out.device_path));
        wide_to_utf8(instance_id_w, out.instance_id, ARRAYSIZE(out.instance_id));

        extract_product_hint(instance_id_w, out.product);
        if (out.product[0] == '\0') {
            ZeroMemory(desc_w, sizeof(desc_w));
            if (!query_instance_string(hdev, &dev_info, SPDRP_FRIENDLYNAME, desc_w, ARRAYSIZE(desc_w))) {
                query_instance_string(hdev, &dev_info, SPDRP_DEVICEDESC, desc_w, ARRAYSIZE(desc_w));
            }
            if (desc_w[0] != L'\0') {
                wide_to_utf8(desc_w, out.product, ARRAYSIZE(out.product));
            } else {
                StringCchCopyA(out.product, ARRAYSIZE(out.product), "Apricorn USB Device");
            }
        }

        out.physical_drive_num = -1;
        if (get_disk_number_from_path(detail->DevicePath, &disk_number)) {
            out.physical_drive_num = disk_number;
        }

        out.read_only = 0;
        if (out.physical_drive_num >= 0) {
            double raw_size_gb = 0.0;
            bool oob_mode = false;
            if (get_physical_drive_metrics(
                    out.physical_drive_num, &raw_size_gb, &oob_mode, &out.read_only, &out.bcd_usb)) {
                out.oob_mode = oob_mode;
                if (!oob_mode && raw_size_gb > 0.0) {
                    out.drive_size_gb = normalize_size_gb(out.id_product, raw_size_gb);
                    out.has_drive_size_gb = out.drive_size_gb > 0;
                }
            }
        }

        letters_w = lookup_drive_letters(&drive_map, out.physical_drive_num);
        wide_to_utf8(letters_w, out.drive_letter, ARRAYSIZE(out.drive_letter));
        if (!out.has_drive_size_gb) {
            double letter_size_gib = 0.0;
            if (get_size_from_drive_letters(out.drive_letter, &letter_size_gib) && letter_size_gib > 0.0) {
                out.drive_size_gb = normalize_size_gb(out.id_product, letter_size_gib);
                out.has_drive_size_gb = out.drive_size_gb > 0;
                if (out.has_drive_size_gb) {
                    out.oob_mode = false;
                }
            }
        }

        ZeroMemory(service_w, sizeof(service_w));
        query_instance_string(hdev, &dev_info, SPDRP_SERVICE, service_w, ARRAYSIZE(service_w));
        classify_transport(instance_id_w, service_w, out.driver_transport);
        if (usb_devinst != 0) {
            classify_usb_controller(usb_devinst, out.usb_controller);
        }

        populate_driver_info(
            dev_info.DevInst,
            out.disk_driver_provider,
            out.disk_driver_version,
            out.disk_driver_inf);
        if (usb_devinst != 0) {
            DWORD reg_value = 0;
            populate_driver_info(
                usb_devinst,
                out.usb_driver_provider,
                out.usb_driver_version,
                out.usb_driver_inf);
            if (get_devnode_reg_dword(usb_devinst, CM_DRP_BUSNUMBER, &reg_value)) {
                out.bus_number = (int)reg_value;
            }
            if (get_devnode_reg_dword(usb_devinst, CM_DRP_ADDRESS, &reg_value)) {
                out.device_address = (int)reg_value;
            }
            if (derive_bus_number_from_location_paths(usb_devinst, &out.bus_number)) {
                if (out.bus_number < 0) {
                    out.bus_number = 0;
                }
            } else if (out.bus_number >= 0) {
                out.bus_number += 1;
            }
            query_connection_metrics_from_parent_hub(
                usb_devinst,
                out.id_vendor,
                out.id_product,
                &out.bcd_usb,
                &out.device_address,
                out.bcd_device);
        }

        if (!vec_push_device(devices, &out)) {
            success = false;
            free(detail);
            break;
        }

        free(detail);
        ++index;
    }

    stats->enumeration_ms = now_ms() - enum_start;
    if (devices->count > 1) {
        qsort(devices->items, devices->count, sizeof(devices->items[0]), compare_devices_by_drive_num);
    }

    SetupDiDestroyDeviceInfoList(hdev);
    free(drive_map.items);
    return success;
}

int wmain(int argc, wchar_t** argv) {
    DeviceVec devices = {0};
    ProfileStats stats;
    bool ok = false;
    bool include_profile = false;
    int i = 0;
    double start = now_ms();

    for (i = 1; i < argc; ++i) {
        if (_wcsicmp(argv[i], L"--profile") == 0) {
            include_profile = true;
        }
    }

    ZeroMemory(&stats, sizeof(stats));
    ok = enumerate_apricorn_devices(&devices, &stats);
    stats.total_ms = now_ms() - start;

    if (!ok) {
        fputs("{\"error\":\"enumeration_failed\"}\n", stderr);
        free(devices.items);
        return 1;
    }

    emit_json(&devices, &stats, include_profile);
    free(devices.items);
    return 0;
}
