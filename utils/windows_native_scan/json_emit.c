#include "json_emit.h"

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
    if (!d->oob_mode && d->file_system[0] != '\0') {
        fputs(",\n        \"fileSystem\": ", stdout);
        json_print_escaped(d->file_system);
    }
    fputs(",\n        \"readOnly\": ", stdout);
    fputs(d->read_only ? "true" : "false", stdout);
    if (d->oob_mode) {
        fputs(",\n        \"scbPartNumber\": \"N/A\"", stdout);
        fputs(",\n        \"hardwareVersion\": \"N/A\"", stdout);
        fputs(",\n        \"modelID\": \"N/A\"", stdout);
        fputs(",\n        \"mcuFW\": \"N/A\"", stdout);
    }
}

int compare_devices_by_drive_num(const void* a, const void* b) {
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

void emit_json(const DeviceVec* devices, const ProfileStats* stats, bool include_profile) {
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
