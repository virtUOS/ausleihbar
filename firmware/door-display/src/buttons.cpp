// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
#include "buttons.h"

#include <Arduino.h>
#include <esp_sleep.h>

#include "board.h"

namespace buttons {

namespace {

constexpr uint8_t PINS[COUNT] = {PIN_BTN_TOP, PIN_BTN_UP, PIN_BTN_DOWN, PIN_BTN_BOTTOM,
                                 PIN_BTN_PRESS};
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t POLL_MS = 5;

bool held(int i) { return digitalRead(PINS[i]) == LOW; }

}  // namespace

const char *name(Button b) {
  switch (b) {
    case TOP: return "top";
    case UP: return "up";
    case DOWN: return "down";
    case BOTTOM: return "bottom";
    case PRESS: return "top";  // rocker press = confirm, like the top button
    default: return "wake";    // UNKNOWN: refresh only
  }
}

void begin() {
  for (uint8_t pin : PINS) pinMode(pin, INPUT);  // external 4.7k pull-ups
}

Button from_wakeup() {
  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_EXT1) return NONE;
  uint64_t status = esp_sleep_get_ext1_wakeup_status();
  Button found = NONE;
  for (int i = 0; i < COUNT; ++i) {
    if (status & (1ULL << PINS[i])) {
      if (found != NONE) return UNKNOWN;  // ambiguous
      found = static_cast<Button>(i);
    }
  }
  return found == NONE ? UNKNOWN : found;
}

Button wait_press(uint32_t timeout_ms) {
  bool stable[COUNT];
  bool last_raw[COUNT];
  uint32_t changed_at[COUNT];
  uint32_t now = millis();
  for (int i = 0; i < COUNT; ++i) {
    stable[i] = last_raw[i] = held(i);
    changed_at[i] = now;
  }
  uint32_t start = now;
  while (millis() - start < timeout_ms) {
    now = millis();
    for (int i = 0; i < COUNT; ++i) {
      bool raw = held(i);
      if (raw != last_raw[i]) {
        last_raw[i] = raw;
        changed_at[i] = now;
      } else if (raw != stable[i] && now - changed_at[i] >= DEBOUNCE_MS) {
        stable[i] = raw;
        if (raw) return static_cast<Button>(i);  // new press
      }
    }
    delay(POLL_MS);
  }
  return NONE;
}

uint64_t wait_release(uint32_t timeout_ms) {
  uint32_t start = millis();
  for (;;) {
    bool any = false;
    for (int i = 0; i < COUNT; ++i) any |= held(i);
    if (!any || millis() - start >= timeout_ms) break;
    delay(POLL_MS);
  }
  uint64_t mask = 0;
  for (int i = 0; i < COUNT; ++i) {
    if (!held(i)) mask |= 1ULL << PINS[i];
  }
  return mask;
}

}  // namespace buttons
