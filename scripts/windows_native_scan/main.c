#include "common.h"

#include "enumerate.h"
#include "json_emit.h"

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
