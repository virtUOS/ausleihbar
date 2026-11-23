// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Persistent device state: the secret in NVS (survives power loss and
// reflashing the app), everything else in RTC memory (survives deep sleep,
// reset on power-up).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace state {

// Resets the RTC state unless the chip woke from deep sleep.
void begin();

// The device secret: 64 lower-case hex chars (32 random bytes), created on
// first use. Call after Wi-Fi is started (the hardware RNG then draws on RF
// noise). Never log it.
const char *secret();
// First 6 hex chars, for debug output only.
void secret_fingerprint(char out[7]);

const char *etag();
void set_etag(const char *etag);
void clear_etag();

// Draw counter: every 10th draw (and the first after power-up) is full.
bool next_draw_must_be_full();
void count_draw();

// Last frame known to be on the panel (nullptr if unknown). Kept across deep
// sleep only on the 2.13" panel (3.9 KB fits RTC memory, the 5.79" frame of
// 26.9 KB does not).
const uint8_t *shown_frame();
void set_shown_frame(const uint8_t *frame);  // nullptr = unknown

bool offline_marker_shown();
void set_offline_marker_shown(bool shown);

}  // namespace state
