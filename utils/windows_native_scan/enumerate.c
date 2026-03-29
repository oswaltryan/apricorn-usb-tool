#include "enumerate.h"

#include "devnode.h"
#include "json_emit.h"
#include "storage.h"
#include "topology.h"

static const GUID GUID_DEVINTERFACE_DISK_LOCAL = {0x53f56307,
                                                  0xb6bf,
                                                  0x11d0,
                                                  {0x94, 0xf2, 0x00, 0xa0, 0xc9, 0x1e, 0xfb, 0x8b}};

bool enumerate_apricorn_devices(DeviceVec* devices, ProfileStats* stats) {
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

    hdev = SetupDiGetClassDevsW(
        &GUID_DEVINTERFACE_DISK_LOCAL, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (hdev == INVALID_HANDLE_VALUE) {
        free_drive_letter_map(&drive_map);
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
        SetupDiGetDeviceInterfaceDetailW(hdev, &if_data, NULL, 0, &required, &dev_info);

        detail = (PSP_DEVICE_INTERFACE_DETAIL_DATA_W)malloc(required);
        if (detail == NULL) {
            success = false;
            break;
        }
        detail->cbSize = sizeof(*detail);
        detail_ok = SetupDiGetDeviceInterfaceDetailW(hdev, &if_data, detail, required, NULL, &dev_info);
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
        if (!out.has_drive_size_gb && !out.oob_mode) {
            double raw_size_gb = 0.0;
            bool oob_mode = false;
            int read_only = out.read_only;
            if (get_device_path_metrics(detail->DevicePath, &raw_size_gb, &oob_mode, &read_only)) {
                out.read_only = read_only;
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
            dev_info.DevInst, out.disk_driver_provider, out.disk_driver_version, out.disk_driver_inf);
        if (usb_devinst != 0) {
            DWORD reg_value = 0;
            populate_driver_info(
                usb_devinst, out.usb_driver_provider, out.usb_driver_version, out.usb_driver_inf);
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
                usb_devinst, out.id_vendor, out.id_product, &out.bcd_usb, &out.device_address, out.bcd_device);
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
    free_drive_letter_map(&drive_map);
    return success;
}
