// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
#include "frame_map.h"

#include <string.h>

namespace frame_map {

void map_small(const uint8_t *frame, uint8_t *ram, bool mirror_x) {
  memset(ram, 0, SMALL_RAM_BYTES);
  for (int y = 0; y < SMALL_H; ++y) {
    for (int x = 0; x < SMALL_W; ++x) {
      if (!get_pixel(frame, SMALL_FRAME_STRIDE, x, y)) continue;
      int col = y;                 // bit position inside the RAM row
      int row = mirror_x ? x : SMALL_W - 1 - x;  // RAM row
      ram[row * SMALL_RAM_STRIDE + col / 8] |= 0x80 >> (col % 8);
    }
  }
}

void map_wide(const uint8_t *frame, uint8_t *mem) {
  memset(mem, 0, WIDE_MEM_BYTES);
  for (int y = 0; y < WIDE_H; ++y) {
    int my = WIDE_H - 1 - y;
    for (int x = 0; x < WIDE_W; ++x) {
      if (!get_pixel(frame, WIDE_FRAME_STRIDE, x, y)) continue;
      int gx = x < WIDE_SEAM ? x : x + 8;  // skip the 8-column seam gap
      int mx = WIDE_MEM_W - 1 - gx;
      mem[my * WIDE_MEM_STRIDE + mx / 8] |= 0x80 >> (mx % 8);
    }
  }
}

// 5x7 glyphs, one byte per column, bit 0 = top row. Only the characters of
// the marker text are needed.
struct Glyph {
  char ch;
  uint8_t cols[5];
};

static const Glyph GLYPHS[] = {
    {'K', {0x7F, 0x08, 0x14, 0x22, 0x41}}, {'V', {0x1F, 0x20, 0x40, 0x20, 0x1F}},
    {'b', {0x7F, 0x48, 0x44, 0x44, 0x38}}, {'d', {0x38, 0x44, 0x44, 0x48, 0x7F}},
    {'e', {0x38, 0x54, 0x54, 0x54, 0x18}}, {'g', {0x0C, 0x52, 0x52, 0x52, 0x3E}},
    {'i', {0x00, 0x44, 0x7D, 0x40, 0x00}}, {'n', {0x7C, 0x08, 0x04, 0x04, 0x78}},
    {'r', {0x7C, 0x08, 0x04, 0x04, 0x08}}, {'u', {0x3C, 0x40, 0x40, 0x20, 0x7C}},
};

static const uint8_t *glyph(char ch) {
  for (const Glyph &g : GLYPHS) {
    if (g.ch == ch) return g.cols;
  }
  return nullptr;  // space / unknown: blank
}

Rect draw_offline_marker(uint8_t *frame, int width, int height, int scale) {
  static const char TEXT[] = "Keine Verbindung";
  const size_t stride = (width + 7) / 8;
  const int len = sizeof(TEXT) - 1;
  const int pad = 2 * scale;
  const int text_w = (len * 6 - 1) * scale;
  const int text_h = 7 * scale;
  Rect r{0, height - (text_h + 2 * pad + 2), text_w + 2 * pad + 1, height - 1};
  if (r.x1 >= width) r.x1 = width - 1;
  if (r.y0 < 0) r.y0 = 0;

  for (int y = r.y0; y <= r.y1; ++y) {
    for (int x = r.x0; x <= r.x1; ++x) {
      bool border = x == r.x0 || x == r.x1 || y == r.y0 || y == r.y1;
      set_pixel(frame, stride, x, y, border);
    }
  }
  const int tx = r.x0 + 1 + pad;
  const int ty = r.y0 + 1 + pad;
  for (int i = 0; i < len; ++i) {
    const uint8_t *cols = glyph(TEXT[i]);
    if (!cols) continue;
    for (int c = 0; c < 5; ++c) {
      for (int row = 0; row < 7; ++row) {
        if (!(cols[c] & (1 << row))) continue;
        for (int dy = 0; dy < scale; ++dy) {
          for (int dx = 0; dx < scale; ++dx) {
            int x = tx + (i * 6 + c) * scale + dx;
            int y = ty + row * scale + dy;
            if (x <= r.x1 && y <= r.y1) set_pixel(frame, stride, x, y, true);
          }
        }
      }
    }
  }
  return r;
}

}  // namespace frame_map
