/**
 * @file main.c
 * @brief Digital Twin Gateway MQTT C Client for Raspberry Pi.
 */

#include "gateway.h"

#include <mosquitto.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static volatile bool g_running = true;
static struct mosquitto *g_mosq = NULL;
static KitDeviceState g_state;
static GatewayConfig g_config;
static bool g_auto_start = false;

static uint64_t get_monotonic_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)(ts.tv_nsec / 1000000ULL);
}

static void handle_signal(int sig) {
    (void)sig;
    g_running = false;
}

static void on_connect(struct mosquitto *mosq, void *obj, int rc) {
    GatewayConfig *cfg = (GatewayConfig *)obj;
    if (rc == 0) {
        printf("[MQTT] Connected to broker %s:%d successfully.\n", cfg->broker_host, cfg->broker_port);
        char cmd_sub_topic[256];
        snprintf(cmd_sub_topic, sizeof(cmd_sub_topic), "lab/kit/%s/cmd/+", cfg->kit_code);
        mosquitto_subscribe(mosq, NULL, cmd_sub_topic, 1);
        printf("[MQTT] Subscribed to command topic: %s\n", cmd_sub_topic);
    } else {
        fprintf(stderr, "[MQTT] Connection failed with code: %d (%s)\n", rc, mosquitto_connack_string(rc));
    }
}

static void on_disconnect(struct mosquitto *mosq, void *obj, int rc) {
    (void)mosq;
    (void)obj;
    printf("[MQTT] Disconnected from broker (rc=%d).\n", rc);
}

static void on_message(struct mosquitto *mosq, void *obj, const struct mosquitto_message *msg) {
    (void)obj;
    if (!msg || !msg->topic || !msg->payload) return;

    char prefix[128];
    snprintf(prefix, sizeof(prefix), "lab/kit/%s/cmd/", g_config.kit_code);

    if (strncmp(msg->topic, prefix, strlen(prefix)) != 0) {
        return; /* Topic does not match this kit's command prefix */
    }

    const char *cmd_name = msg->topic + strlen(prefix);
    char *payload_str = (char *)malloc(msg->payloadlen + 1);
    if (!payload_str) return;

    memcpy(payload_str, msg->payload, msg->payloadlen);
    payload_str[msg->payloadlen] = '\0';

    printf("[CMD] Received command [%s]: %s\n", cmd_name, payload_str);

    if (strcmp(cmd_name, "reset") == 0) {
        char action[32];
        if (json_get_string(payload_str, "action", action, sizeof(action))) {
            if (strcmp(action, "start") == 0 || strcmp(action, "stop") == 0 || strcmp(action, "calib") == 0) {
                state_handle_reset(&g_state, action);
                printf("[CMD] Applied reset action: '%s'. in_use: %s\n", action, g_state.is_in_use ? "true" : "false");
            } else {
                fprintf(stderr, "[CMD] Invalid reset action: '%s'\n", action);
            }
        } else {
            fprintf(stderr, "[CMD] Deprecated or empty reset payload rejected.\n");
        }
    } else if (strcmp(cmd_name, "power") == 0) {
        char action[32];
        if (json_get_string(payload_str, "action", action, sizeof(action))) {
            if (strcmp(action, "on") == 0 || strcmp(action, "off") == 0) {
                state_handle_power(&g_state, action);
                printf("[CMD] Set AC Power to: '%s'. power_on: %s\n", action, g_state.power_on ? "true" : "false");
            } else {
                fprintf(stderr, "[CMD] Invalid power action: '%s'\n", action);
            }
        }
    } else if (strcmp(cmd_name, "voltage") == 0) {
        int voltage = 0;
        if (json_get_int(payload_str, "voltage", &voltage)) {
            if (state_handle_voltage(&g_state, voltage)) {
                printf("[CMD] Voltage set to %dV. Measured: %.2fV\n", voltage, g_state.measured_voltage);
            } else {
                fprintf(stderr, "[CMD] Invalid voltage level: %dV (must be 0, 3, 6, 9, 12)\n", voltage);
            }
        }
    } else if (strcmp(cmd_name, "scale") == 0) {
        char scale[32];
        if (json_get_string(payload_str, "scale", scale, sizeof(scale))) {
            if (state_handle_scale(&g_state, scale)) {
                printf("[CMD] Scale set to: '%s' mT\n", scale);
            } else {
                fprintf(stderr, "[CMD] Invalid scale enum: '%s'\n", scale);
            }
        }
    } else if (strcmp(cmd_name, "ruler") == 0) {
        int pos = 0;
        if (json_get_int(payload_str, "position", &pos)) {
            if (state_handle_ruler(&g_state, pos)) {
                printf("[CMD] Ruler moved to %d mm. Field: %.6f mT\n", pos, g_state.magnetic_field);
            } else {
                fprintf(stderr, "[CMD] Invalid ruler position: %d (must be 0..300 mm)\n", pos);
            }
        }
    } else if (strcmp(cmd_name, "shutdown") == 0) {
        char action[32];
        if (json_get_string(payload_str, "action", action, sizeof(action)) && strcmp(action, "shutdown") == 0) {
            printf("[CMD] Admin SHUTDOWN command received!\n");
            state_handle_shutdown(&g_state);
            g_running = false; /* Request graceful process exit */
        }
    }

    /* Publish immediate telemetry feedback upon valid command while in-use */
    pthread_mutex_lock(&g_state.lock);
    if (g_state.is_in_use && !g_state.is_shutdown) {
        char tel_buf[512];
        int len = build_telemetry_json(&g_state, tel_buf, sizeof(tel_buf));
        char tel_topic[256];
        snprintf(tel_topic, sizeof(tel_topic), "lab/kit/%s/telemetry", g_config.kit_code);
        mosquitto_publish(mosq, NULL, tel_topic, len, tel_buf, 0, false);
    }
    pthread_mutex_unlock(&g_state.lock);

    free(payload_str);
}

static void parse_cli_args(int argc, char **argv) {
    memset(&g_config, 0, sizeof(GatewayConfig));
    snprintf(g_config.broker_host, sizeof(g_config.broker_host), "%s", DEFAULT_BROKER_HOST);
    g_config.broker_port = DEFAULT_BROKER_PORT;
    g_config.keepalive = DEFAULT_KEEPALIVE;
    snprintf(g_config.kit_code, sizeof(g_config.kit_code), "%s", DEFAULT_KIT_CODE);

    /* Check Environment overrides */
    char *env_host = getenv("MQTT_BROKER_HOST");
    if (env_host && strlen(env_host) > 0) {
        snprintf(g_config.broker_host, sizeof(g_config.broker_host), "%s", env_host);
    }
    char *env_port = getenv("MQTT_BROKER_PORT");
    if (env_port && atoi(env_port) > 0) {
        g_config.broker_port = atoi(env_port);
    }
    char *env_kit = getenv("KIT_CODE");
    if (env_kit && strlen(env_kit) > 0) {
        snprintf(g_config.kit_code, sizeof(g_config.kit_code), "%s", env_kit);
    }

    int opt;
    while ((opt = getopt(argc, argv, "h:p:k:u:P:a")) != -1) {
        switch (opt) {
            case 'h':
                snprintf(g_config.broker_host, sizeof(g_config.broker_host), "%s", optarg);
                break;
            case 'p':
                g_config.broker_port = atoi(optarg);
                break;
            case 'k':
                snprintf(g_config.kit_code, sizeof(g_config.kit_code), "%s", optarg);
                break;
            case 'u':
                snprintf(g_config.username, sizeof(g_config.username), "%s", optarg);
                g_config.use_auth = true;
                break;
            case 'P':
                snprintf(g_config.password, sizeof(g_config.password), "%s", optarg);
                g_config.use_auth = true;
                break;
            case 'a':
                g_auto_start = true;
                break;
            default:
                fprintf(stderr, "Usage: %s [-h host] [-p port] [-k kit_code] [-u user] [-P pass] [-a auto-start]\n", argv[0]);
                exit(EXIT_FAILURE);
        }
    }
}

int main(int argc, char **argv) {
    parse_cli_args(argc, argv);
    state_init(&g_state, g_config.kit_code);

    if (g_auto_start) {
        state_handle_reset(&g_state, "start");
    }

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    printf("============================================================\n");
    printf(" Digital Twin Gateway C Client\n");
    printf(" Broker:    %s:%d\n", g_config.broker_host, g_config.broker_port);
    printf(" Kit Code:  %s\n", g_config.kit_code);
    if (g_state.is_in_use) {
        printf(" Status:    IN-USE (Auto-start enabled, publishing 2 Hz)\n");
    } else {
        printf(" Status:    IDLE (Waiting for 'reset start' command)\n");
        printf(" -> Tip:    Send command '{\"action\":\"start\"}' to begin,\n");
        printf("            or re-run with '-a' to auto-start immediately.\n");
    }
    printf(" Telemetry: 2 Hz (mỗi 500 ms) khi in-use\n");
    printf(" Heartbeat: Định kỳ mỗi 5000 ms (5s) khi in-use\n");
    printf("============================================================\n");

    mosquitto_lib_init();

    char client_id[128];
    snprintf(client_id, sizeof(client_id), "gateway_c_%s_%d", g_config.kit_code, getpid());

    g_mosq = mosquitto_new(client_id, true, &g_config);
    if (!g_mosq) {
        fprintf(stderr, "Error: Unable to initialize mosquitto instance\n");
        mosquitto_lib_cleanup();
        return 1;
    }

    if (g_config.use_auth) {
        mosquitto_username_pw_set(g_mosq, g_config.username, g_config.password);
    }

    mosquitto_connect_callback_set(g_mosq, on_connect);
    mosquitto_disconnect_callback_set(g_mosq, on_disconnect);
    mosquitto_message_callback_set(g_mosq, on_message);

    int rc = mosquitto_connect_async(g_mosq, g_config.broker_host, g_config.broker_port, g_config.keepalive);
    if (rc != MOSQ_ERR_SUCCESS) {
        fprintf(stderr, "Error: mosquitto_connect_async failed: %s\n", mosquitto_strerror(rc));
    }

    mosquitto_loop_start(g_mosq);

    char tel_topic[256];
    snprintf(tel_topic, sizeof(tel_topic), "lab/kit/%s/telemetry", g_config.kit_code);
    char hb_topic[256];
    snprintf(hb_topic, sizeof(hb_topic), "lab/kit/%s/heartbeat", g_config.kit_code);

    uint64_t last_tel_ms = 0;
    uint64_t last_hb_ms = 0;

    while (g_running) {
        usleep(10000); /* 10 ms sleep tick */
        uint64_t now_ms = get_monotonic_ms();

        pthread_mutex_lock(&g_state.lock);
        bool in_use = g_state.is_in_use && !g_state.is_shutdown;

        /* Telemetry Loop: 2 Hz (every 500 ms) while in-use */
        if (in_use && (now_ms - last_tel_ms >= TELEMETRY_INTERVAL_MS)) {
            char buf[512];
            int len = build_telemetry_json(&g_state, buf, sizeof(buf));
            mosquitto_publish(g_mosq, NULL, tel_topic, len, buf, 0, false);
            last_tel_ms = now_ms;
        }

        /* Heartbeat Loop: every 5000 ms (5.0s) while in-use */
        if (in_use && (now_ms - last_hb_ms >= HEARTBEAT_INTERVAL_MS)) {
            char buf[256];
            int len = build_heartbeat_json(g_config.kit_code, buf, sizeof(buf));
            mosquitto_publish(g_mosq, NULL, hb_topic, len, buf, 0, false);
            last_hb_ms = now_ms;
        }
        pthread_mutex_unlock(&g_state.lock);
    }

    printf("\nShutting down Digital Twin Gateway C Client...\n");
    mosquitto_disconnect(g_mosq);
    mosquitto_loop_stop(g_mosq, true);
    mosquitto_destroy(g_mosq);
    mosquitto_lib_cleanup();
    state_destroy(&g_state);

    printf("Gateway client exited cleanly.\n");
    return 0;
}
