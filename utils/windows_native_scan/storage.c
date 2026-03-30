#include "storage.h"

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

static bool add_drive_letter_for_disk(DriveLetterVec* map,
                                      int disk_number,
                                      wchar_t drive_letter) {
    size_t j = 0;
    DWORD idx = 0;
    bool inserted = false;

    for (j = 0; j < map->count; ++j) {
        if (map->items[j].disk_number == disk_number) {
            idx = (DWORD)j;
            inserted = true;
            break;
        }
    }

    if (!inserted) {
        DriveLetterEntry entry;
        entry.disk_number = disk_number;
        entry.letters[0] = L'\0';
        if (!vec_push_drive_letter(map, &entry)) {
            return false;
        }
        idx = (DWORD)(map->count - 1);
    }

    {
        wchar_t token[3];
        token[0] = drive_letter;
        token[1] = L':';
        token[2] = L'\0';
        append_drive_letter_token(map->items[idx].letters, ARRAYSIZE(map->items[idx].letters), token);
    }

    return true;
}

static bool is_not_formatted_letters(const wchar_t* letters) {
    if (letters == NULL) {
        return true;
    }
    return _wcsicmp(letters, L"Not Formatted") == 0;
}

static void trim_token_inplace(wchar_t* token) {
    size_t len;
    wchar_t* start = token;
    if (token == NULL || token[0] == L'\0') {
        return;
    }
    while (*start != L'\0' && iswspace(*start)) {
        ++start;
    }
    if (start != token) {
        memmove(token, start, (wcslen(start) + 1) * sizeof(*token));
    }
    len = wcslen(token);
    while (len > 0 && iswspace(token[len - 1])) {
        token[len - 1] = L'\0';
        --len;
    }
}

static bool csv_contains_token_ci(const wchar_t* csv, const wchar_t* token) {
    const wchar_t* cursor = csv;
    wchar_t parsed[64];
    size_t idx = 0;

    if (csv == NULL || token == NULL || token[0] == L'\0') {
        return false;
    }

    while (*cursor != L'\0') {
        idx = 0;
        while (*cursor != L'\0' && *cursor != L',' && idx + 1 < ARRAYSIZE(parsed)) {
            parsed[idx++] = *cursor++;
        }
        parsed[idx] = L'\0';
        trim_token_inplace(parsed);
        if (parsed[0] != L'\0' && _wcsicmp(parsed, token) == 0) {
            return true;
        }
        if (*cursor == L',') {
            ++cursor;
        }
    }
    return false;
}

static void append_csv_token_unique(wchar_t* csv, size_t cap, const wchar_t* token) {
    if (token == NULL || token[0] == L'\0') {
        return;
    }
    if (csv[0] == L'\0') {
        StringCchCopyW(csv, cap, token);
        return;
    }
    if (csv_contains_token_ci(csv, token)) {
        return;
    }
    StringCchCatW(csv, cap, L", ");
    StringCchCatW(csv, cap, token);
}

static bool parse_drive_letter_token(const wchar_t* token, wchar_t root[4]) {
    wchar_t trimmed[16];
    StringCchCopyW(trimmed, ARRAYSIZE(trimmed), token);
    trim_token_inplace(trimmed);
    if (trimmed[0] == L'\0') {
        return false;
    }
    if (!iswalpha(trimmed[0])) {
        return false;
    }
    if (trimmed[1] != L':') {
        return false;
    }
    root[0] = towupper(trimmed[0]);
    root[1] = L':';
    root[2] = L'\\';
    root[3] = L'\0';
    return true;
}

static bool classify_disk_without_drive_letters(int disk_number,
                                                wchar_t* filesystem_out,
                                                size_t filesystem_out_cap) {
    if (filesystem_out == NULL || filesystem_out_cap == 0) {
        return false;
    }
    (void)disk_number;
    StringCchCopyW(filesystem_out, filesystem_out_cap, L"Unallocated");
    return true;
}

bool get_disk_number_from_path(const wchar_t* path, int* disk_number_out) {
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

void collect_drive_letter_map(DriveLetterVec* map) {
    DWORD mask = GetLogicalDrives();
    int i = 0;
    for (i = 0; i < 26; ++i) {
        wchar_t drive_letter;
        wchar_t root[4];
        wchar_t open_path[8];
        HANDLE h = INVALID_HANDLE_VALUE;
        BYTE extents_buf[sizeof(VOLUME_DISK_EXTENTS) + sizeof(DISK_EXTENT) * 31];
        VOLUME_DISK_EXTENTS* extents = (VOLUME_DISK_EXTENTS*)extents_buf;
        STORAGE_DEVICE_NUMBER number;
        DWORD out_bytes = 0;
        DWORD e = 0;
        bool mapped_via_extents = false;

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

        ZeroMemory(extents_buf, sizeof(extents_buf));
        if (DeviceIoControl(h,
                            IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
                            NULL,
                            0,
                            extents_buf,
                            (DWORD)sizeof(extents_buf),
                            &out_bytes,
                            NULL) &&
            out_bytes >= sizeof(VOLUME_DISK_EXTENTS) &&
            extents->NumberOfDiskExtents > 0) {
            for (e = 0; e < extents->NumberOfDiskExtents; ++e) {
                if (!add_drive_letter_for_disk(
                        map, (int)extents->Extents[e].DiskNumber, drive_letter)) {
                    CloseHandle(h);
                    return;
                }
                mapped_via_extents = true;
            }
        }

        if (!mapped_via_extents) {
            ZeroMemory(&number, sizeof(number));
            if (DeviceIoControl(h,
                                IOCTL_STORAGE_GET_DEVICE_NUMBER,
                                NULL,
                                0,
                                &number,
                                (DWORD)sizeof(number),
                                &out_bytes,
                                NULL)) {
                if (!add_drive_letter_for_disk(map, (int)number.DeviceNumber, drive_letter)) {
                    CloseHandle(h);
                    return;
                }
            }
        }
        CloseHandle(h);
    }
}

const wchar_t* lookup_drive_letters(const DriveLetterVec* map, int disk_number) {
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

void free_drive_letter_map(DriveLetterVec* map) {
    free(map->items);
    map->items = NULL;
    map->count = 0;
    map->cap = 0;
}

bool get_physical_drive_metrics(int disk_number,
                                double* size_gb_raw_out,
                                bool* oob_mode_out,
                                int* read_only_out,
                                double* bcd_usb_out) {
    wchar_t path[64];
    HANDLE h = INVALID_HANDLE_VALUE;
    GET_LENGTH_INFORMATION len_info;
    DISK_GEOMETRY_EX geometry_ex;
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
    StringCchPrintfW(path, ARRAYSIZE(path), L"\\\\.\\PhysicalDrive%d", disk_number);
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
    if (len_ok) {
        bytes = (unsigned long long)len_info.Length.QuadPart;
    } else {
        ZeroMemory(&geometry_ex, sizeof(geometry_ex));
        out_bytes = 0;
        if (DeviceIoControl(h,
                            IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
                            NULL,
                            0,
                            &geometry_ex,
                            (DWORD)sizeof(geometry_ex),
                            &out_bytes,
                            NULL)) {
            len_ok = TRUE;
            bytes = (unsigned long long)geometry_ex.DiskSize.QuadPart;
        }
    }
    if (!len_ok) {
        bytes = 0ULL;
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

bool get_device_path_metrics(const wchar_t* device_path,
                             double* size_gb_raw_out,
                             bool* oob_mode_out,
                             int* read_only_out) {
    HANDLE h = INVALID_HANDLE_VALUE;
    GET_LENGTH_INFORMATION len_info;
    DISK_GEOMETRY_EX geometry_ex;
    DWORD out_bytes = 0;
    BOOL len_ok = FALSE;
    BOOL writable_ok = FALSE;
    unsigned long long bytes = 0ULL;
    double gib = 0.0;

    if (device_path == NULL || device_path[0] == L'\0') {
        return false;
    }

    *read_only_out = 0;
    *size_gb_raw_out = 0.0;
    *oob_mode_out = false;

    h = CreateFileW(device_path,
                    0,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    NULL,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    NULL);
    if (h == INVALID_HANDLE_VALUE) {
        return false;
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
    if (len_ok) {
        bytes = (unsigned long long)len_info.Length.QuadPart;
    } else {
        ZeroMemory(&geometry_ex, sizeof(geometry_ex));
        out_bytes = 0;
        if (DeviceIoControl(h,
                            IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
                            NULL,
                            0,
                            &geometry_ex,
                            (DWORD)sizeof(geometry_ex),
                            &out_bytes,
                            NULL)) {
            len_ok = TRUE;
            bytes = (unsigned long long)geometry_ex.DiskSize.QuadPart;
        }
    }
    if (!len_ok) {
        bytes = 0ULL;
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

bool get_size_from_drive_letters(const char* letters_csv, double* size_gib_out) {
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

bool derive_filesystem_for_disk(int disk_number,
                                const wchar_t* drive_letters,
                                wchar_t* filesystem_out,
                                size_t filesystem_out_cap) {
    const wchar_t* cursor = drive_letters;
    wchar_t token[16];
    size_t idx = 0;
    wchar_t root[4];
    wchar_t fs_name[MAX_PATH];
    BOOL fs_ok = FALSE;
    bool saw_letter = false;

    if (filesystem_out == NULL || filesystem_out_cap == 0) {
        return false;
    }
    filesystem_out[0] = L'\0';

    if (drive_letters == NULL || drive_letters[0] == L'\0' || is_not_formatted_letters(drive_letters)) {
        return classify_disk_without_drive_letters(disk_number, filesystem_out, filesystem_out_cap);
    }

    while (*cursor != L'\0') {
        idx = 0;
        while (*cursor != L'\0' && *cursor != L',' && idx + 1 < ARRAYSIZE(token)) {
            token[idx++] = *cursor++;
        }
        token[idx] = L'\0';
        if (*cursor == L',') {
            ++cursor;
        }

        if (!parse_drive_letter_token(token, root)) {
            continue;
        }
        saw_letter = true;

        fs_name[0] = L'\0';
        fs_ok = GetVolumeInformationW(root,
                                      NULL,
                                      0,
                                      NULL,
                                      NULL,
                                      NULL,
                                      fs_name,
                                      ARRAYSIZE(fs_name));
        if (!fs_ok) {
            fs_name[0] = L'\0';
            fs_ok = GetVolumeInformationW(root,
                                          NULL,
                                          0,
                                          NULL,
                                          NULL,
                                          NULL,
                                          fs_name,
                                          ARRAYSIZE(fs_name));
        }
        if (fs_ok && fs_name[0] != L'\0') {
            append_csv_token_unique(filesystem_out, filesystem_out_cap, fs_name);
        }
    }

    if (filesystem_out[0] != L'\0') {
        return true;
    }
    if (saw_letter) {
        StringCchCopyW(filesystem_out, filesystem_out_cap, L"RAW");
        return true;
    }

    return classify_disk_without_drive_letters(disk_number, filesystem_out, filesystem_out_cap);
}
