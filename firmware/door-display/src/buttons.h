// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// The keys on the right edge: top button, rocker (up / down / press), bottom
// button. All active low with external pull-ups (see board_*.h).
#pragma once

#include <stdint.h>

namespace buttons {

// TOP..PRESS are physical keys (COUNT of them). UNKNOWN is an ext1 wake that
// cannot be pinned to exactly one key; it is never a key of its own.
enum Button : int8_t { NONE = -1, TOP = 0, UP, DOWN, BOTTOM, PRESS, COUNT, UNKNOWN };

// Server name of a button: "top", "up", "down", "bottom". The rocker press
// acts like the top button ("top"); UNKNOWN is sent as "wake" (refresh only)
// so an undecodable wake can never confirm an action.
const char *name(Button b);

void begin();

// The button that woke the chip from deep sleep (ext1), UNKNOWN when several
// or none can be told apart, NONE if the wake was not ext1.
Button from_wakeup();

// Waits up to ``timeout_ms`` for a new debounced press; NONE on timeout.
// A key already held when the wait starts must be released first.
Button wait_press(uint32_t timeout_ms);

// Waits (bounded) until no key is held; returns the ext1 mask of keys that
// are released (a stuck key is left out so it cannot re-wake the chip at once).
uint64_t wait_release(uint32_t timeout_ms);

}  // namespace buttons
