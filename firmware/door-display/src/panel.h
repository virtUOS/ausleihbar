// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Panel drivers (panel_small.cpp / panel_wide.cpp, one is compiled per env).
// Frames are logical server frames: FRAME_WIDTH x FRAME_HEIGHT, row-major,
// MSB = leftmost pixel, bit 1 = black.
#pragma once

#include <stdint.h>

namespace panel {

// Whether the controller supports a partial (non-flashing) refresh here.
bool supports_partial();

// Full refresh: the whole panel is redrawn (flashes once).
bool show_full(const uint8_t *frame);

// Partial refresh: only pixels that differ between ``old_frame`` (what the
// panel shows now) and ``frame`` are driven. Falls back to a full refresh
// when partial refresh is not supported.
bool show_partial(const uint8_t *frame, const uint8_t *old_frame);

// Controller deep sleep, panel power off (call before ESP deep sleep).
void off();

}  // namespace panel
