// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// 5.79" CrowPanel: two cascaded SSD1683 (master = left half of the controller
// RAM image, slave = right half; commands with bit 7 set address the slave).
// Written for this project from the SSD1683 datasheet; command sequences and
// RAM window values follow Elecrow's CrowPanel examples (no licence stated,
// see THIRD-PARTY-LICENSES.md):
// https://github.com/Elecrow-RD/CrowPanel-ESP32-5.79-E-paper-HMI-Display-with-272-792
//   example/arduino/Examples/5.79_PWR/EPD_Init.cpp (EPD_SetRAMMP/MA/SP/SA,
//   EPD_Display, EPD_Update, EPD_PartUpdate)
#if defined(BOARD_WIDE)

#include <Arduino.h>

#include "board.h"
#include "epd_bus.h"
#include "frame_map.h"
#include "panel.h"

namespace panel {

namespace {

using frame_map::WIDE_HALF_BYTES;
using frame_map::WIDE_MEM_BYTES;

uint8_t mem_new[WIDE_MEM_BYTES];
uint8_t mem_old[WIDE_MEM_BYTES];

constexpr int BUSY_LEVEL = HIGH;  // SSD1683: BUSY high while busy
constexpr uint32_t INIT_TIMEOUT_MS = 3000;
constexpr uint32_t FULL_TIMEOUT_MS = 15000;
constexpr uint32_t PARTIAL_TIMEOUT_MS = 6000;

bool init() {
  epd_bus::power_on();
  epd_bus::reset();
  if (!epd_bus::wait_idle(BUSY_LEVEL, INIT_TIMEOUT_MS)) return false;
  epd_bus::command(0x12);  // software reset (both controllers)
  if (!epd_bus::wait_idle(BUSY_LEVEL, INIT_TIMEOUT_MS)) return false;
  epd_bus::command(0x18);  // internal temperature sensor
  epd_bus::data(0x80);
  // Master window: X bytes 0..49 increasing, Y 271..0 decreasing,
  // address counter moving in Y direction (entry mode 0x05).
  epd_bus::command(0x11);
  epd_bus::data(0x05);
  const uint8_t mx[] = {0x00, 0x31};
  epd_bus::command_data(0x44, mx, sizeof mx);
  const uint8_t my[] = {0x0F, 0x01, 0x00, 0x00};
  epd_bus::command_data(0x45, my, sizeof my);
  // Slave window: X bytes 49..0 decreasing (mirrored half), same Y.
  epd_bus::command(0x91);
  epd_bus::data(0x04);
  const uint8_t sx[] = {0x31, 0x00};
  epd_bus::command_data(0xC4, sx, sizeof sx);
  const uint8_t sy[] = {0x0F, 0x01, 0x00, 0x00};
  epd_bus::command_data(0xC5, sy, sizeof sy);
  return true;
}

void master_counter() {
  epd_bus::command(0x4E);
  epd_bus::data(0x00);
  const uint8_t y[] = {0x0F, 0x01};
  epd_bus::command_data(0x4F, y, sizeof y);
}

void slave_counter() {
  epd_bus::command(0xCE);
  epd_bus::data(0x31);
  const uint8_t y[] = {0x0F, 0x01};
  epd_bus::command_data(0xCF, y, sizeof y);
}

// ``bw`` = 0x24 (new image) or 0x26 (previous image); the slave uses | 0x80.
// ``invert`` writes the negative (used for the "previous" RAM of a full
// refresh, see show_full).
void write_ram(uint8_t bw, const uint8_t *mem, bool invert = false) {
  // SSD1683 RAM: bit 1 = white.
  const uint8_t mask = invert ? 0x00 : 0xFF;
  master_counter();
  epd_bus::stream(bw, WIDE_HALF_BYTES, [mem, mask](size_t k) {
    return static_cast<uint8_t>(frame_map::wide_stream_byte(mem, false, k) ^ mask);
  });
  slave_counter();
  epd_bus::stream(bw | 0x80, WIDE_HALF_BYTES, [mem, mask](size_t k) {
    return static_cast<uint8_t>(frame_map::wide_stream_byte(mem, true, k) ^ mask);
  });
}

bool update(uint8_t mode, uint32_t timeout_ms) {
  epd_bus::command(0x22);
  epd_bus::data(mode);
  epd_bus::command(0x20);
  return epd_bus::wait_idle(BUSY_LEVEL, timeout_ms);
}

void border(uint8_t value) {
  // Master only, as Elecrow's examples never address the slave's border.
  // TODO(verify on hardware): border waveform 0x05 (full) / 0x80 (partial).
  epd_bus::command(0x3C);
  epd_bus::data(value);
}

}  // namespace

bool supports_partial() { return true; }

bool show_full(const uint8_t *frame) {
  frame_map::map_wide(frame, mem_new);
  if (!init()) return false;
  border(0x05);
  write_ram(0x24, mem_new);
  // The panel's mode-1 waveform only drives pixels whose "previous" bit differs
  // from the new one (verified on hardware: writing the same image to both
  // RAMs left the old picture in place). The negative as "previous" makes
  // every pixel switch, like Elecrow's EPD_Display_Clear (0x24 = FF, 0x26 = 00).
  write_ram(0x26, mem_new, true);
  return update(0xF7, FULL_TIMEOUT_MS);  // display mode 1, all off after
}

bool show_partial(const uint8_t *frame, const uint8_t *old_frame) {
  frame_map::map_wide(frame, mem_new);
  frame_map::map_wide(old_frame, mem_old);
  if (!init()) return false;
  border(0x80);
  write_ram(0x26, mem_old);
  write_ram(0x24, mem_new);
  // Display mode 2. Elecrow's EPD_PartUpdate uses 0xDC after a fast-mode init
  // that already loaded the temperature; 0xFC also reads the sensor.
  // TODO(verify on hardware): partial refresh quality with 0xFC.
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

}  // namespace panel

#endif  // BOARD_WIDE
