/**
 * @file test_c_gateway.c
 * @brief Unit tests for C gateway protocol and device state.
 */

#include "gateway.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void test_json_parsing(void) {
    const char *payload_reset = "{\"action\":\"start\"}";
    char action[32] = {0};
    assert(json_get_string(payload_reset, "action", action, sizeof(action)));
    assert(strcmp(action, "start") == 0);

    const char *payload_voltage = "{\"voltage\":6}";
    int voltage = -1;
    assert(json_get_int(payload_voltage, "voltage", &voltage));
    assert(voltage == 6);

    const char *payload_ruler = "{\"position\":150}";
    int ruler = -1;
    assert(json_get_int(payload_ruler, "position", &ruler));
    assert(ruler == 150);

    const char *payload_scale = "{\"scale\":\"199.9\"}";
    char scale[16] = {0};
    assert(json_get_string(payload_scale, "scale", scale, sizeof(scale)));
    assert(strcmp(scale, "199.9") == 0);

    printf("[PASS] JSON parsing tests passed.\n");
}

static void test_state_and_physics(void) {
    KitDeviceState state;
    state_init(&state, "KIT-001");
    assert(!state.is_in_use);
    assert(!state.power_on);

    /* 1. Start attempt */
    state_handle_reset(&state, "start");
    assert(state.is_in_use);
    assert(!state.power_on);

    /* 2. Set power ON, voltage 6V, ruler 150mm */
    state_handle_power(&state, "on");
    assert(state.power_on);

    assert(state_handle_voltage(&state, 6));
    assert(state_handle_ruler(&state, 150));

    /* Check physics calculation against guide examples */
    assert(fabs(state.measured_voltage - 6.07) < 0.1);
    assert(fabs(state.measured_current_ma - 125.5) < 1.0);
    assert(fabs(state.magnetic_field - 123.456789) < 2.0);

    /* 3. Ruler move to 0 mm (edge of solenoid) decreases magnetic field */
    double center_field = state.magnetic_field;
    assert(state_handle_ruler(&state, 0));
    assert(state.magnetic_field < center_field);

    /* 4. Turn OFF power */
    state_handle_power(&state, "off");
    assert(!state.power_on);
    assert(state.measured_voltage == 0.0);
    assert(state.measured_current_ma == 0.0);
    assert(state.magnetic_field == 0.0);

    /* 5. Stop attempt */
    state_handle_reset(&state, "stop");
    assert(!state.is_in_use);

    /* 6. Shutdown */
    state_handle_shutdown(&state);
    assert(state.is_shutdown);

    state_destroy(&state);
    printf("[PASS] State & physics lifecycle tests passed.\n");
}

static void test_payload_generation(void) {
    KitDeviceState state;
    state_init(&state, "KIT-001");
    state_handle_reset(&state, "start");
    state_handle_power(&state, "on");
    state_handle_voltage(&state, 6);
    state_handle_ruler(&state, 150);

    char buf[512];
    int len = build_telemetry_json(&state, buf, sizeof(buf));
    assert(len > 0);
    assert(strstr(buf, "\"kit_code\":\"KIT-001\"") != NULL);
    assert(strstr(buf, "\"current_ma\":125.5") != NULL);
    assert(strstr(buf, "\"power_on\":true") != NULL);
    assert(strstr(buf, "\"scale\":\"199.9\"") != NULL);
    assert(strstr(buf, "\"ruler_position\":150") != NULL);

    char hb_buf[256];
    int hb_len = build_heartbeat_json("KIT-001", hb_buf, sizeof(hb_buf));
    assert(hb_len > 0);
    assert(strstr(hb_buf, "\"kit_code\":\"KIT-001\"") != NULL);

    state_destroy(&state);
    printf("[PASS] Payload generation tests passed.\n");
}

int main(void) {
    printf("Running C Gateway unit tests...\n");
    test_json_parsing();
    test_state_and_physics();
    test_payload_generation();
    printf("All C tests passed successfully!\n");
    return 0;
}

