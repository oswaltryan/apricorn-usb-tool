#include "common.h"

static const char* EXCLUDED_PIDS[] = {"0221", "0211", "0301"};

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

static void uppercase_hex4(char* value) {
    size_t i = 0;
    for (i = 0; i < 4 && value[i] != '\0'; ++i) {
        value[i] = (char)toupper((unsigned char)value[i]);
    }
}

double now_ms(void) {
    static LARGE_INTEGER freq = {0};
    LARGE_INTEGER counter = {0};
    if (freq.QuadPart == 0) {
        QueryPerformanceFrequency(&freq);
    }
    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart * 1000.0 / (double)freq.QuadPart;
}

int normalize_size_gb(const char* pid, double raw_gib) {
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

bool vec_push_device(DeviceVec* vec, const ApricornDevice* item) {
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

bool is_excluded_pid(const char* pid) {
    size_t i = 0;
    for (i = 0; i < ARRAYSIZE(EXCLUDED_PIDS); ++i) {
        if (_stricmp(pid, EXCLUDED_PIDS[i]) == 0) {
            return true;
        }
    }
    return false;
}

void wide_to_utf8(const wchar_t* ws, char* out, size_t out_cap) {
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

bool parse_hex4_after_token(const wchar_t* text, const wchar_t* token, char out[5]) {
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

void extract_serial_segment(const wchar_t* instance_id, char out[128]) {
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

void extract_product_hint(const wchar_t* instance_id, char out[128]) {
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
    while (*p != L'\0' && *p != L'&' && *p != L'#' && i + 1 < ARRAYSIZE(token)) {
        token[i++] = (*p == L'_') ? L' ' : *p;
        ++p;
    }
    token[i] = L'\0';
    wide_to_utf8(token, out, 128);
}
