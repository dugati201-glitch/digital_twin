/**
 * @file gateway.h
 * @brief Header definitions for Digital Twin Gateway C client using MQTT.
 */

#ifndef GATEWAY_H
#define GATEWAY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <pthread.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DEFAULT_BROKER_HOST "mqtt.mysignage.vn"
#define DEFAULT_BROKER_PORT 1883
#define DEFAULT_KEEPALIVE   60
#define DEFAULT_KIT_CODE    "KIT-001"

#define TELEMETRY_INTERVAL_MS 500   /* 2 Hz = 500 ms */
#define HEARTBEAT_INTERVAL_MS 5000  /* 5.0 seconds */

/**
 * @brief Experiment kit device and physical state structure.
 */
typedef struct {
    char kit_code[64];
    bool is_in_use;
    bool is_shutdown;

    /* Physical parameters */
    bool power_on;
    int target_voltage;          /* 0, 3, 6, 9, 12 V */
    double measured_voltage;     /* e.g. 6.07 V */
    double measured_current_ma;  /* e.g. 125.5 mA */
    double magnetic_field;       /* e.g. 123.456789 mT */
    char scale[16];              /* "1.999", "19.99", "199.9" */
    int ruler_position;          /* 0..300 mm */

    pthread_mutex_t lock;
} KitDeviceState;

/**
 * @brief Gateway configuration structure.
 */
typedef struct {
    char broker_host[256];
    int broker_port;
    int keepalive;
    char kit_code[64];
    char username[128];
    char password[128];
    bool use_auth;
} GatewayConfig;

/* State management functions */
void state_init(KitDeviceState *state, const char *kit_code);
void state_destroy(KitDeviceState *state);
void state_handle_reset(KitDeviceState *state, const char *action);
void state_handle_power(KitDeviceState *state, const char *action);
bool state_handle_voltage(KitDeviceState *state, int voltage);
bool state_handle_scale(KitDeviceState *state, const char *scale);
bool state_handle_ruler(KitDeviceState *state, int position);
void state_handle_shutdown(KitDeviceState *state);
void state_recalculate_physics(KitDeviceState *state);

/* Protocol and formatting functions */
void get_utc_iso_timestamp(char *buf, size_t max_len);
int build_telemetry_json(const KitDeviceState *state, char *out_buf, size_t max_len);
int build_heartbeat_json(const char *kit_code, char *out_buf, size_t max_len);

/* Simple JSON helper functions */
bool json_get_string(const char *json, const char *key, char *out_val, size_t max_len);
bool json_get_int(const char *json, const char *key, int *out_val);

#ifdef __cplusplus
}
#endif

#endif /* GATEWAY_H */

