/**
 * @file protocol.c
 * @brief MQTT payload building and minimal JSON extraction functions.
 */

#include "gateway.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

void get_utc_iso_timestamp(char *buf, size_t max_len) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    struct tm tm_info;
    gmtime_r(&ts.tv_sec, &tm_info);
    int ms = (int)(ts.tv_nsec / 1000000L);
    snprintf(buf, max_len, "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
             tm_info.tm_year + 1900, tm_info.tm_mon + 1, tm_info.tm_mday,
             tm_info.tm_hour, tm_info.tm_min, tm_info.tm_sec, ms);
}

int build_telemetry_json(const KitDeviceState *state, char *out_buf, size_t max_len) {
    char ts[64];
    get_utc_iso_timestamp(ts, sizeof(ts));

    return snprintf(
        out_buf, max_len,
        "{\"kit_code\":\"%s\","
        "\"ts\":\"%s\","
        "\"voltage\":%.2f,"
        "\"current_ma\":%.1f,"
        "\"power_on\":%s,"
        "\"magnetic_field\":%.6f,"
        "\"scale\":\"%s\","
        "\"ruler_position\":%d}",
        state->kit_code,
        ts,
        state->measured_voltage,
        state->measured_current_ma,
        state->power_on ? "true" : "false",
        state->magnetic_field,
        state->scale,
        state->ruler_position
    );
}

int build_heartbeat_json(const char *kit_code, char *out_buf, size_t max_len) {
    char ts[64];
    get_utc_iso_timestamp(ts, sizeof(ts));

    return snprintf(
        out_buf, max_len,
        "{\"kit_code\":\"%s\","
        "\"ts\":\"%s\"}",
        kit_code,
        ts
    );
}

bool json_get_string(const char *json, const char *key, char *out_val, size_t max_len) {
    if (!json || !key || !out_val || max_len == 0) return false;

    char search_pattern[128];
    snprintf(search_pattern, sizeof(search_pattern), "\"%s\"", key);

    const char *pos = strstr(json, search_pattern);
    if (!pos) return false;

    pos += strlen(search_pattern);
    while (*pos && (*pos == ' ' || *pos == '\t' || *pos == '\r' || *pos == '\n' || *pos == ':')) {
        pos++;
    }

    if (*pos != '\"') return false;
    pos++; /* skip opening quote */

    size_t idx = 0;
    while (*pos && *pos != '\"' && idx + 1 < max_len) {
        if (*pos == '\\' && *(pos + 1)) {
            pos++; /* skip escape */
        }
        out_val[idx++] = *pos++;
    }
    out_val[idx] = '\0';
    return (*pos == '\"');
}

bool json_get_int(const char *json, const char *key, int *out_val) {
    if (!json || !key || !out_val) return false;

    char search_pattern[128];
    snprintf(search_pattern, sizeof(search_pattern), "\"%s\"", key);

    const char *pos = strstr(json, search_pattern);
    if (!pos) return false;

    pos += strlen(search_pattern);
    while (*pos && (*pos == ' ' || *pos == '\t' || *pos == '\r' || *pos == '\n' || *pos == ':')) {
        pos++;
    }

    char *endptr = NULL;
    long val = strtol(pos, &endptr, 10);
    if (endptr == pos) return false;

    *out_val = (int)val;
    return true;
}

