// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// 2.13" CrowPanel: SSD1680 (default) or JD79661 (SMALL_CONTROLLER_JD79661=1).
// Written for this project from the SSD1680 datasheet; command sequences,
// register values and the JD79661 waveform tables follow Elecrow's CrowPanel
// examples (no licence stated, see THIRD-PARTY-LICENSES.md):
// https://github.com/Elecrow-RD/CrowPanel-ESP32-2.13-E-paper-HMI-Display-with-122-250
//   SSD1680: example/arduino/Example Code/2.13_partial_refresh/EPD_Init.cpp
//   JD79661: example/arduino-v1.2/main/EPD_Init.cpp
#if defined(BOARD_SMALL)

#include <Arduino.h>

#include "board.h"
#include "epd_bus.h"
#include "frame_map.h"
#include "panel.h"

namespace panel {

namespace {

using frame_map::SMALL_RAM_BYTES;

uint8_t ram_new[SMALL_RAM_BYTES];
#if !SMALL_CONTROLLER_JD79661
uint8_t ram_old[SMALL_RAM_BYTES];
#endif

constexpr uint32_t INIT_TIMEOUT_MS = 3000;
constexpr uint32_t FULL_TIMEOUT_MS = 15000;
constexpr uint32_t PARTIAL_TIMEOUT_MS = 6000;

#if !SMALL_CONTROLLER_JD79661
// ---------------------------------------------------------------- SSD1680
constexpr int BUSY_LEVEL = HIGH;  // SSD1680: BUSY high while busy

bool init() {
  epd_bus::power_on();
  epd_bus::reset();
  if (!epd_bus::wait_idle(BUSY_LEVEL, INIT_TIMEOUT_MS)) return false;
  epd_bus::command(0x12);  // software reset
  if (!epd_bus::wait_idle(BUSY_LEVEL, INIT_TIMEOUT_MS)) return false;
  const uint8_t driver_output[] = {0xF9, 0x00, 0x00};  // 250 gate lines
  epd_bus::command_data(0x01, driver_output, sizeof driver_output);
  epd_bus::command(0x11);  // data entry: X increment, Y increment
  epd_bus::data(0x03);
  const uint8_t ram_x[] = {0x00, 0x0F};  // 16 bytes = 128 source bits
  epd_bus::command_data(0x44, ram_x, sizeof ram_x);
  const uint8_t ram_y[] = {0x00, 0x00, 0xF9, 0x00};  // rows 0..249
  epd_bus::command_data(0x45, ram_y, sizeof ram_y);
  epd_bus::command(0x18);  // internal temperature sensor
  epd_bus::data(0x80);
  return epd_bus::wait_idle(BUSY_LEVEL, INIT_TIMEOUT_MS);
}

void write_ram(uint8_t cmd, const uint8_t *ram) {
  epd_bus::command(0x4E);  // RAM X counter
  epd_bus::data(0x00);
  const uint8_t y[] = {0x00, 0x00};
  epd_bus::command_data(0x4F, y, sizeof y);
  // SSD1680 RAM: bit 1 = white.
  epd_bus::stream(cmd, SMALL_RAM_BYTES, [ram](size_t i) { return static_cast<uint8_t>(~ram[i]); });
}

bool update(uint8_t mode, uint32_t timeout_ms) {
  epd_bus::command(0x22);
  epd_bus::data(mode);
  epd_bus::command(0x20);
  return epd_bus::wait_idle(BUSY_LEVEL, timeout_ms);
}

}  // namespace

bool supports_partial() { return true; }

bool show_full(const uint8_t *frame) {
  frame_map::map_small(frame, ram_new);
  if (!init()) return false;
  // TODO(verify on hardware): border waveform 0x05 (follow LUT, white) for
  // full refreshes, 0x80 (VCOM, untouched) for partial ones.
  epd_bus::command(0x3C);
  epd_bus::data(0x05);
  write_ram(0x24, ram_new);
  write_ram(0x26, ram_new);
  // Clock + analog on, load temperature + LUT, display mode 1, all off after.
  return update(0xF7, FULL_TIMEOUT_MS);
}

bool show_partial(const uint8_t *frame, const uint8_t *old_frame) {
  frame_map::map_small(frame, ram_new);
  frame_map::map_small(old_frame, ram_old);
  if (!init()) return false;
  epd_bus::command(0x3C);
  epd_bus::data(0x80);
  write_ram(0x26, ram_old);  // "previous" image for display mode 2
  write_ram(0x24, ram_new);
  // Display mode 2 (partial), as in Elecrow's EPD_PartUpdate; analog stays on
  // until off() or the next reset.
  return update(0xFC, PARTIAL_TIMEOUT_MS);
}

void off() {
  if (epd_bus::powered()) {
    update(0x83, INIT_TIMEOUT_MS);  // analog + clock off
    epd_bus::command(0x10);         // deep sleep mode 1
    epd_bus::data(0x01);
    delay(5);
  }
  epd_bus::power_off();
}

#else
// ---------------------------------------------------------------- JD79661
constexpr int BUSY_LEVEL = LOW;  // JD79661: BUSY low while busy

// "GC" (full) waveform of Elecrow's example: VCOM, WW, BW, WB, BB.
const uint8_t LUT_VCOM[] = {0x01, 0x00, 0x14, 0x14, 0x01, 0x00, 0x00, 0x01};
const uint8_t LUT_WW[] = {0x01, 0x60, 0x14, 0x14, 0x01, 0x00, 0x00, 0x01};
const uint8_t LUT_BW[] = {0x01, 0x20, 0x14, 0x14, 0x01, 0x00, 0x00, 0x01};
const uint8_t LUT_WB[] = {0x01, 0x10, 0x14, 0x14, 0x01, 0x00, 0x00, 0x01};
const uint8_t LUT_BB[] = {0x01, 0x90, 0x14, 0x14, 0x01, 0x00, 0x00, 0x01};
constexpr size_t LUT_LEN = 56;  // 8 used bytes, rest zero

void write_lut(uint8_t reg, const uint8_t *head) {
  epd_bus::stream(reg, LUT_LEN, [head](size_t i) { return i < 8 ? head[i] : static_cast<uint8_t>(0); });
}

bool init() {
  epd_bus::power_on();
  epd_bus::reset(100, 100);
  if (!epd_bus::wait_idle(BUSY_LEVEL, INIT_TIMEOUT_MS)) return false;
  const uint8_t psr[] = {0xF7, 0x8A};
  epd_bus::command_data(0x00, psr, sizeof psr);
  const uint8_t pwr[] = {0x03, 0x00, 0x3F, 0x3F, 0x03};
  epd_bus::command_data(0x01, pwr, sizeof pwr);
  epd_bus::command(0x03);
  epd_bus::data(0x00);
  const uint8_t booster[] = {0x27, 0x27, 0x2F};
  epd_bus::command_data(0x06, booster, sizeof booster);
  epd_bus::command(0x30);
  epd_bus::data(0x0D);
  epd_bus::command(0x60);
  epd_bus::data(0x22);
  epd_bus::command(0x82);
  epd_bus::data(0x07);
  epd_bus::command(0xE3);
  epd_bus::data(0x88);
  epd_bus::command(0x41);
  epd_bus::data(0x00);
  const uint8_t tres[] = {0x80, 0x00, 0xFA};  // 128 x 250
  epd_bus::command_data(0x61, tres, sizeof tres);
  const uint8_t gss[] = {0x00, 0x00, 0x00};
  epd_bus::command_data(0x65, gss, sizeof gss);
  epd_bus::command(0x50);
  epd_bus::data(0xD7);
  return true;
}

}  // namespace

// Only Elecrow's full ("GC") waveform is used; their "DU" waveform swaps the
// BW/WB tables on every call, which is not understood well enough to rely on.
bool supports_partial() { return false; }

bool show_full(const uint8_t *frame) {
  frame_map::map_small(frame, ram_new);
  if (!init()) return false;
  epd_bus::stream(0x10, SMALL_RAM_BYTES, [](size_t) { return static_cast<uint8_t>(0x00); });
  // JD79661 RAM as in Elecrow's example: bit 1 = black.
  epd_bus::stream(0x13, SMALL_RAM_BYTES, [](size_t i) { return ram_new[i]; });
  write_lut(0x20, LUT_VCOM);
  write_lut(0x21, LUT_WW);
  write_lut(0x22, LUT_BW);
  write_lut(0x23, LUT_WB);
  write_lut(0x24, LUT_BB);
  epd_bus::command(0x17);  // display refresh (auto sequence)
  epd_bus::data(0xA5);
  return epd_bus::wait_idle(BUSY_LEVEL, FULL_TIMEOUT_MS);
}

bool show_partial(const uint8_t *frame, const uint8_t *) { return show_full(frame); }

void off() {
  if (epd_bus::powered()) {
    epd_bus::command(0x07);  // deep sleep
    epd_bus::data(0xA5);
    delay(20);
  }
  epd_bus::power_off();
}

#endif

}  // namespace panel

#endif  // BOARD_SMALL
