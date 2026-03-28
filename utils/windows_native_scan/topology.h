#ifndef WINDOWS_NATIVE_SCAN_TOPOLOGY_H
#define WINDOWS_NATIVE_SCAN_TOPOLOGY_H

#include "common.h"

void classify_transport(const wchar_t* instance_id, const wchar_t* service, char out[16]);
bool query_connection_metrics_from_parent_hub(DEVINST usb_devinst,
                                              const char* expected_vid,
                                              const char* expected_pid,
                                              double* bcd_usb_out,
                                              int* device_address_out,
                                              char bcd_device_out[5]);
void classify_usb_controller(DEVINST usb_devinst, char out[32]);
bool find_usb_identity(DEVINST start_devinst,
                       char vid_out[5],
                       char pid_out[5],
                       char bcd_out[5],
                       char serial_out[128],
                       DEVINST* usb_devinst_out);

#endif
