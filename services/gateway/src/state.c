/**
 * @file state.c
 * @brief Device state transitions and solenoid physical modeling.
 */

#include "gateway.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

void state_init(KitDeviceState *state, const char *kit_code) {
    memset(state, 0, sizeof(KitDeviceState));
    snprintf(state->kit_code, sizeof(state->kit_code), "%s", kit_code ? kit_code : DEFAULT_KIT_CODE);

    state->is_in_use = false;
    state->is_shutdown = false;
    state->power_on = false;
    state->target_voltage = 0;
    state->measured_voltage = 0.0;
    state->measured_current_ma = 0.0;
    state->magnetic_field = 0.0;
    snprintf(state->scale, sizeof(state->scale), "199.9");
    state->ruler_position = 150; /* Initialized at solenoid center */

    pthread_mutex_init(&state->lock, NULL);
    state_recalculate_physics(state);
}

void state_destroy(KitDeviceState *state) {
    pthread_mutex_destroy(&state->lock);
}

void state_handle_reset(KitDeviceState *state, const char *action) {
    pthread_mutex_lock(&state->lock);
    if (strcmp(action, "start") == 0) {
        state->is_in_use = true;
        state->is_shutdown = false;
        state->power_on = false;
        state->target_voltage = 0;
        state_recalculate_physics(state);
    } else if (strcmp(action, "stop") == 0) {
        state->is_in_use = false;
        state->power_on = false;
        state->target_voltage = 0;
        state_recalculate_physics(state);
    } else if (strcmp(action, "calib") == 0) {
        /* Calibrate Tesla meter offset */
        state_recalculate_physics(state);
    }
    pthread_mutex_unlock(&state->lock);
}

void state_handle_power(KitDeviceState *state, const char *action) {
    pthread_mutex_lock(&state->lock);
    if (strcmp(action, "on") == 0) {
        state->power_on = true;
    } else if (strcmp(action, "off") == 0) {
        state->power_on = false;
    }
    state_recalculate_physics(state);
    pthread_mutex_unlock(&state->lock);
}

bool state_handle_voltage(KitDeviceState *state, int voltage) {
    if (voltage != 0 && voltage != 3 && voltage != 6 && voltage != 9 && voltage != 12) {
        return false;
    }
    pthread_mutex_lock(&state->lock);
    state->target_voltage = voltage;
    state_recalculate_physics(state);
    pthread_mutex_unlock(&state->lock);
    return true;
}

bool state_handle_scale(KitDeviceState *state, const char *scale) {
    if (strcmp(scale, "1.999") != 0 && strcmp(scale, "19.99") != 0 && strcmp(scale, "199.9") != 0) {
        return false;
    }
    pthread_mutex_lock(&state->lock);
    snprintf(state->scale, sizeof(state->scale), "%s", scale);
    pthread_mutex_unlock(&state->lock);
    return true;
}

bool state_handle_ruler(KitDeviceState *state, int position) {
    if (position < 0 || position > 300) {
        return false;
    }
    pthread_mutex_lock(&state->lock);
    state->ruler_position = position;
    state_recalculate_physics(state);
    pthread_mutex_unlock(&state->lock);
    return true;
}

void state_handle_shutdown(KitDeviceState *state) {
    pthread_mutex_lock(&state->lock);
    state->is_shutdown = true;
    state->is_in_use = false;
    state->power_on = false;
    state->target_voltage = 0;
    state_recalculate_physics(state);
    pthread_mutex_unlock(&state->lock);
}

void state_recalculate_physics(KitDeviceState *state) {
    /* Safe conditions */
    if (!state->power_on || state->target_voltage == 0) {
        state->measured_voltage = 0.0;
        state->measured_current_ma = 0.0;
        state->magnetic_field = 0.0;
        return;
    }

    /* Solenoid coil resistance ~ 48.36 ohm */
    const double coil_resistance = 48.36;
    const double radius_mm = 25.0;
    const double length_mm = 300.0;
    const double field_scale = 0.99728876;

    /* Measured voltage with realistic slight load regulation variation */
    state->measured_voltage = round((state->target_voltage * 1.011 + 0.004) * 100.0) / 100.0;

    /* Current in mA */
    double current = (state->measured_voltage / coil_resistance) * 1000.0;
    state->measured_current_ma = round(current * 10.0) / 10.0;

    /* Finite solenoid field profile along central axis */
    double x = (double)state->ruler_position;
    double term1 = x / sqrt(x * x + radius_mm * radius_mm);
    double d = length_mm - x;
    double term2 = d / sqrt(d * d + radius_mm * radius_mm);
    double geometric = 0.5 * (term1 + term2);

    double b = state->measured_current_ma * field_scale * geometric;
    state->magnetic_field = (b < 0.0) ? 0.0 : round(b * 1000000.0) / 1000000.0;
}

