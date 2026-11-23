// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Hardware-free conversion of the server frame into the controllers' RAM
// layout (host-tested in test/host). All buffers here use bit 1 = black;
// the panel drivers invert where a controller wants bit 1 = white.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace frame_map {

// --- 2.13": server frame 250x122 (stride 32) -> controller RAM ---------------
// Layout of Elecrow's 2.13" examples (EPD_DrawPoint, USE_HORIZONTIAL 2):
// RAM row r (0..249) = logical column 249 - r, RAM bit c (0..121, MSB first in
// each byte) = logical row c. 16 bytes per RAM row.
constexpr int SMALL_W = 250;
constexpr int SMALL_H = 122;
constexpr size_t SMALL_FRAME_STRIDE = (SMALL_W + 7) / 8;  // 32
constexpr size_t SMALL_RAM_STRIDE = 16;
constexpr size_t SMALL_RAM_ROWS = 250;
constexpr size_t SMALL_RAM_BYTES = SMALL_RAM_STRIDE * SMALL_RAM_ROWS;  // 4000

void map_small(const uint8_t *frame, uint8_t *ram);

// --- 5.79": server frame 792x272 (stride 99) -> two SSD1683 RAMs -------------
// Elecrow's 5.79" examples draw into an 800x272 memory image rotated by 180°
// (Paint_SetPixel, Rotation 180) with an 8-pixel gap at logical x = 396 (the
// seam between the two controllers), then stream it column-byte by column-byte:
// master = memory byte columns 0..49, slave = 50..99, each column top to
// bottom (EPD_Display).
constexpr int WIDE_W = 792;
constexpr int WIDE_H = 272;
constexpr size_t WIDE_FRAME_STRIDE = (WIDE_W + 7) / 8;  // 99
constexpr int WIDE_SEAM = 396;
constexpr int WIDE_MEM_W = 800;
constexpr size_t WIDE_MEM_STRIDE = WIDE_MEM_W / 8;  // 100
constexpr size_t WIDE_MEM_ROWS = 272;
constexpr size_t WIDE_MEM_BYTES = WIDE_MEM_STRIDE * WIDE_MEM_ROWS;  // 27200
constexpr size_t WIDE_HALF_COLS = WIDE_MEM_STRIDE / 2;               // 50
constexpr size_t WIDE_HALF_BYTES = WIDE_HALF_COLS * WIDE_MEM_ROWS;   // 13600

void map_wide(const uint8_t *frame, uint8_t *mem);

// k-th byte (0 <= k < WIDE_HALF_BYTES) sent to the master / slave controller.
inline uint8_t wide_stream_byte(const uint8_t *mem, bool slave, size_t k) {
  size_t line = k % WIDE_MEM_ROWS;
  size_t col = k / WIDE_MEM_ROWS + (slave ? WIDE_HALF_COLS : 0);
  return mem[line * WIDE_MEM_STRIDE + col];
}

// --- Logical frame helpers ---------------------------------------------------
inline bool get_pixel(const uint8_t *frame, size_t stride, int x, int y) {
  return frame[y * stride + x / 8] & (0x80 >> (x % 8));
}

inline void set_pixel(uint8_t *frame, size_t stride, int x, int y, bool black) {
  uint8_t bit = 0x80 >> (x % 8);
  if (black) {
    frame[y * stride + x / 8] |= bit;
  } else {
    frame[y * stride + x / 8] &= ~bit;
  }
}

struct Rect {
  int x0, y0, x1, y1;  // inclusive
};

// Draws the "Keine Verbindung" marker (white box, black border and text) at
// the bottom-left corner of a logical frame; returns the box.
Rect draw_offline_marker(uint8_t *frame, int width, int height, int scale);

}  // namespace frame_map
