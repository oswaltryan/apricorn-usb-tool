#include "version_probe.h"

#define IOCTL_SCSI_PASS_THROUGH_DIRECT_LOCAL 0x4D014
#define SCSI_IOCTL_DATA_IN_LOCAL 1

typedef struct {
    USHORT Length;
    UCHAR ScsiStatus;
    UCHAR PathId;
    UCHAR TargetId;
    UCHAR Lun;
    UCHAR CdbLength;
    UCHAR SenseInfoLength;
    UCHAR DataIn;
    ULONG DataTransferLength;
    ULONG TimeOutValue;
    PVOID DataBuffer;
    ULONG SenseInfoOffset;
    UCHAR Cdb[16];
} SCSI_PASS_THROUGH_DIRECT_LOCAL;

typedef struct {
    SCSI_PASS_THROUGH_DIRECT_LOCAL sptd;
    UCHAR sense[32];
} SPTD_WITH_SENSE_LOCAL;

static bool is_ascii_digit(unsigned char c) {
    return c >= '0' && c <= '9';
}

static void set_version_defaults(ApricornDevice* device_out) {
    StringCchCopyA(device_out->scb_part_number, ARRAYSIZE(device_out->scb_part_number), "N/A");
    StringCchCopyA(device_out->hardware_version, ARRAYSIZE(device_out->hardware_version), "N/A");
    StringCchCopyA(device_out->model_id, ARRAYSIZE(device_out->model_id), "N/A");
    StringCchCopyA(device_out->mcu_fw, ARRAYSIZE(device_out->mcu_fw), "N/A");
    StringCchCopyA(device_out->bridge_fw, ARRAYSIZE(device_out->bridge_fw), "N/A");
}

static bool run_probe_on_path(const wchar_t* path,
                              BYTE* data_out,
                              size_t data_cap,
                              DWORD* open_error_out,
                              DWORD* ioctl_error_out,
                              double* open_ms_out,
                              double* ioctl_ms_out) {
    HANDLE h = INVALID_HANDLE_VALUE;
    SPTD_WITH_SENSE_LOCAL req;
    DWORD returned = 0;
    BYTE cdb[6] = {0x3C, 0x01, 0x00, 0x00, 0x00, 0x00};
    double open_start = 0.0;
    double ioctl_start = 0.0;

    *open_error_out = 0;
    *ioctl_error_out = 0;
    if (open_ms_out != NULL) {
        *open_ms_out = 0.0;
    }
    if (ioctl_ms_out != NULL) {
        *ioctl_ms_out = 0.0;
    }

    open_start = now_ms();
    h = CreateFileW(path,
                    GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    NULL,
                    OPEN_EXISTING,
                    0,
                    NULL);
    if (open_ms_out != NULL) {
        *open_ms_out = now_ms() - open_start;
    }
    if (h == INVALID_HANDLE_VALUE) {
        *open_error_out = GetLastError();
        return false;
    }

    ZeroMemory(&req, sizeof(req));
    req.sptd.Length = sizeof(SCSI_PASS_THROUGH_DIRECT_LOCAL);
    req.sptd.CdbLength = (UCHAR)sizeof(cdb);
    req.sptd.SenseInfoLength = (UCHAR)sizeof(req.sense);
    req.sptd.DataIn = SCSI_IOCTL_DATA_IN_LOCAL;
    req.sptd.DataTransferLength = (ULONG)data_cap;
    req.sptd.TimeOutValue = 5;
    req.sptd.DataBuffer = data_out;
    req.sptd.SenseInfoOffset = sizeof(SCSI_PASS_THROUGH_DIRECT_LOCAL);
    CopyMemory(req.sptd.Cdb, cdb, sizeof(cdb));

    ioctl_start = now_ms();
    if (!DeviceIoControl(h,
                         IOCTL_SCSI_PASS_THROUGH_DIRECT_LOCAL,
                         &req,
                         (DWORD)sizeof(req),
                         &req,
                         (DWORD)sizeof(req),
                         &returned,
                         NULL)) {
        if (ioctl_ms_out != NULL) {
            *ioctl_ms_out = now_ms() - ioctl_start;
        }
        *ioctl_error_out = GetLastError();
        CloseHandle(h);
        return false;
    }
    if (ioctl_ms_out != NULL) {
        *ioctl_ms_out = now_ms() - ioctl_start;
    }

    CloseHandle(h);
    return true;
}

static void parse_version_payload(const BYTE* payload, size_t payload_len, ApricornDevice* out) {
    size_t i = 0;

    if (payload_len >= 4) {
        StringCchPrintfA(out->bridge_fw, ARRAYSIZE(out->bridge_fw), "%02X%02X", payload[2], payload[3]);
    }

    for (i = 0; i + 13 < payload_len; ++i) {
        if (!is_ascii_digit(payload[i]) ||
            !is_ascii_digit(payload[i + 1]) ||
            payload[i + 2] != '-' ||
            !is_ascii_digit(payload[i + 3]) ||
            !is_ascii_digit(payload[i + 4]) ||
            !is_ascii_digit(payload[i + 5]) ||
            !is_ascii_digit(payload[i + 6]) ||
            !is_ascii_digit(payload[i + 7]) ||
            !is_ascii_digit(payload[i + 8]) ||
            !is_ascii_digit(payload[i + 9]) ||
            !is_ascii_digit(payload[i + 10]) ||
            !is_ascii_digit(payload[i + 11]) ||
            !is_ascii_digit(payload[i + 12]) ||
            !is_ascii_digit(payload[i + 13])) {
            continue;
        }

        StringCchPrintfA(out->scb_part_number,
                         ARRAYSIZE(out->scb_part_number),
                         "%c%c-%c%c%c%c",
                         payload[i],
                         payload[i + 1],
                         payload[i + 3],
                         payload[i + 4],
                         payload[i + 5],
                         payload[i + 6]);
        StringCchPrintfA(out->model_id, ARRAYSIZE(out->model_id), "%c%c", payload[i + 8], payload[i + 7]);
        StringCchPrintfA(out->hardware_version,
                         ARRAYSIZE(out->hardware_version),
                         "%c%c",
                         payload[i + 10],
                         payload[i + 9]);
        StringCchPrintfA(out->mcu_fw,
                         ARRAYSIZE(out->mcu_fw),
                         "%d.%d.%d",
                         (int)(payload[i + 13] - '0'),
                         (int)(payload[i + 12] - '0'),
                         (int)(payload[i + 11] - '0'));
        return;
    }
}

bool probe_device_version(const wchar_t* interface_path,
                          int physical_drive_num,
                          ApricornDevice* device_out,
                          VersionProbeMeta* meta_out) {
    BYTE payload[1024];
    wchar_t physical_path[64];
    DWORD open_error = 0;
    DWORD ioctl_error = 0;
    DWORD interface_open_error = 0;
    DWORD interface_ioctl_error = 0;
    DWORD physical_open_error = 0;
    DWORD physical_ioctl_error = 0;
    double interface_open_ms = 0.0;
    double interface_ioctl_ms = 0.0;
    double physical_open_ms = 0.0;
    double physical_ioctl_ms = 0.0;
    double parse_start = 0.0;
    bool ok = false;

    device_out->version_probe_attempted = true;
    set_version_defaults(device_out);

    if (meta_out != NULL) {
        ZeroMemory(meta_out, sizeof(*meta_out));
        meta_out->attempted = true;
    }

    ZeroMemory(payload, sizeof(payload));
    if (interface_path != NULL && interface_path[0] != L'\0') {
        if (meta_out != NULL) {
            meta_out->interface_attempted = true;
        }
        ok = run_probe_on_path(interface_path,
                               payload,
                               sizeof(payload),
                               &interface_open_error,
                               &interface_ioctl_error,
                               &interface_open_ms,
                               &interface_ioctl_ms);
        if (meta_out != NULL) {
            meta_out->interface_success = ok;
        }
    }

    if (!ok && physical_drive_num >= 0) {
        if (meta_out != NULL) {
            meta_out->physical_attempted = true;
        }
        StringCchPrintfW(physical_path, ARRAYSIZE(physical_path), L"\\\\.\\PhysicalDrive%d", physical_drive_num);
        ok = run_probe_on_path(physical_path,
                               payload,
                               sizeof(payload),
                               &physical_open_error,
                               &physical_ioctl_error,
                               &physical_open_ms,
                               &physical_ioctl_ms);
        if (meta_out != NULL) {
            meta_out->physical_success = ok;
        }
    }

    if (meta_out != NULL) {
        meta_out->interface_open_ms = interface_open_ms;
        meta_out->interface_ioctl_ms = interface_ioctl_ms;
        meta_out->interface_open_error = interface_open_error;
        meta_out->interface_ioctl_error = interface_ioctl_error;
        meta_out->physical_open_ms = physical_open_ms;
        meta_out->physical_ioctl_ms = physical_ioctl_ms;
        meta_out->physical_open_error = physical_open_error;
        meta_out->physical_ioctl_error = physical_ioctl_error;
    }

    if (physical_open_error != 0 || physical_ioctl_error != 0 || (meta_out != NULL && meta_out->physical_attempted)) {
        open_error = physical_open_error;
        ioctl_error = physical_ioctl_error;
    } else {
        open_error = interface_open_error;
        ioctl_error = interface_ioctl_error;
    }

    if (meta_out != NULL) {
        meta_out->open_error = open_error;
        meta_out->ioctl_error = ioctl_error;
        meta_out->has_payload = ok;
    }

    if (!ok) {
        return false;
    }

    parse_start = now_ms();
    parse_version_payload(payload, sizeof(payload), device_out);
    if (meta_out != NULL) {
        meta_out->parse_ms = now_ms() - parse_start;
    }
    return true;
}
