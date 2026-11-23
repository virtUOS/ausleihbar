// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// The keys on the right edge: top button, rocker (up / down / press), bottom
// button. All active low with external pull-ups (see board_*.h).
#pragma once

#include <stdint.h>

namespace buttons {

enum Button : int8_t { NONE = -1, TOP = 0, UP, DOWN, BOTTOM, PRESS, COUNT };

// Server name of a button ("top", "up", "down", "bottom"). The rocker press
// has no action on the server and is sent as "wake" (refresh only), so a
// slip while rocking can never confirm a check-out.
const char *name(Button b);

void begin();

// The button that woke the chip from deep sleep (ext1), PRESS ("wake") when
// several or none can be told apart, NONE if the wake was not ext1.
Button from_wakeup();

// Waits up to ``timeout_ms`` for a new debounced press; NONE on timeout.
// A key already held when the wait starts must be released first.
Button wait_press(uint32_t timeout_ms);

// Waits (bounded) until no key is held; returns the ext1 mask of keys that
// are released (a stuck key is left out so it cannot re-wake the chip at once).
uint64_t wait_release(uint32_t timeout_ms);

}  // namespace buttons
