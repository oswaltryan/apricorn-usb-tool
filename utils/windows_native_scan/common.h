#ifndef WINDOWS_NATIVE_SCAN_COMMON_H
#define WINDOWS_NATIVE_SCAN_COMMON_H

#ifndef _CRT_SECURE_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#endif

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif

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
    char file_system[64];
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

double now_ms(void);
bool vec_push_device(DeviceVec* vec, const ApricornDevice* item);
bool is_excluded_pid(const char* pid);
void wide_to_utf8(const wchar_t* ws, char* out, size_t out_cap);
bool parse_hex4_after_token(const wchar_t* text, const wchar_t* token, char out[5]);
void extract_serial_segment(const wchar_t* instance_id, char out[128]);
void extract_product_hint(const wchar_t* instance_id, char out[128]);
int normalize_size_gb(const char* pid, double raw_gib);

#endif
