// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Low-level e-paper bus: panel power switch, reset, 4-wire SPI writes and a
// bounded BUSY wait (never hangs a battery device on a wrong controller).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace epd_bus {

void power_on();   // panel power on, SPI up, pins configured
void power_off();  // SPI down, signal pins high-Z, panel power off (held in deep sleep)
bool powered();  // power_on() called and not switched off since
void reset(uint32_t low_ms = 10, uint32_t settle_ms = 10);

void command(uint8_t cmd);
void data(uint8_t value);
void data(const uint8_t *values, size_t len);
void command_data(uint8_t cmd, const uint8_t *values, size_t len);

// Streams ``count`` bytes produced by ``next(i)`` after a command (CS stays low).
template <typename Fn>
void stream(uint8_t cmd, size_t count, Fn next);
void begin_data();
void write_byte(uint8_t value);
void end_data();

// Waits until BUSY shows idle. busy_level = level of the BUSY pin while busy.
// Returns false after timeout_ms.
bool wait_idle(int busy_level, uint32_t timeout_ms);

template <typename Fn>
void stream(uint8_t cmd, size_t count, Fn next) {
  command(cmd);
  begin_data();
  for (size_t i = 0; i < count; ++i) write_byte(next(i));
  end_data();
}

}  // namespace epd_bus
