#ifndef WINDOWS_NATIVE_SCAN_STORAGE_H
#define WINDOWS_NATIVE_SCAN_STORAGE_H

#include "common.h"

bool get_disk_number_from_path(const wchar_t* path, int* disk_number_out);
void collect_drive_letter_map(DriveLetterVec* map);
const wchar_t* lookup_drive_letters(const DriveLetterVec* map, int disk_number);
void free_drive_letter_map(DriveLetterVec* map);
bool get_physical_drive_metrics(int disk_number,
                                double* size_gb_raw_out,
                                bool* oob_mode_out,
                                int* read_only_out,
                                double* bcd_usb_out);
bool get_size_from_drive_letters(const char* letters_csv, double* size_gib_out);

#endif
