// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Host test for src/frame_map.cpp: compares the fast frame -> RAM mapping with
// a pixel-by-pixel re-implementation of the drawing routines in Elecrow's
// CrowPanel examples (2.13": EPD_DrawPoint with USE_HORIZONTIAL 2;
// 5.79": Paint_SetPixel with Rotation 180 on an 800x272 image + EPD_Display's
// column-wise streaming). Build and run:
//   c++ -std=c++17 -I../../src test_frame_map.cpp ../../src/frame_map.cpp \
//       -o test_frame_map && ./test_frame_map
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "frame_map.h"

using namespace frame_map;

static int failures = 0;
#define CHECK(cond, ...)            \
  do {                              \
    if (!(cond)) {                  \
      std::printf("FAIL: " __VA_ARGS__); \
      std::printf("\n");            \
      ++failures;                   \
    }                               \
  } while (0)

static std::vector<uint8_t> random_frame(size_t bytes, unsigned seed) {
  std::vector<uint8_t> f(bytes);
  std::srand(seed);
  for (auto &b : f) b = static_cast<uint8_t>(std::rand());
  return f;
}

// Elecrow 2.13": EPD_W 250, EPD_H 122, USE_HORIZONTIAL 2, BLACK sets the bit.
static void elecrow_small_point(uint8_t *img, int x, int y, bool black) {
  const int EPD_W = 250, EPD_H = 122;
  int xpoint = y;
  int ypoint = EPD_W - x - 1;
  int addr = xpoint / 8 + ypoint * ((EPD_H % 8 == 0) ? (EPD_H / 8) : (EPD_H / 8 + 1));
  if (black) img[addr] |= (0x80 >> (xpoint % 8));
  else img[addr] &= ~(0x80 >> (xpoint % 8));
}

// Elecrow 5.79": Paint_SetPixel, Rotation 180, widthMemory 800, heightMemory
// 272, buffer bit 1 = white (BLACK clears the bit).
static void elecrow_wide_point(uint8_t *img, int x, int y, bool black) {
  const int widthMemory = 800, heightMemory = 272, widthByte = 100;
  if (x >= 396) x += 8;
  int X = widthMemory - x - 1;
  int Y = heightMemory - y - 1;
  int addr = X / 8 + Y * widthByte;
  if (black) img[addr] &= ~(0x80 >> (X % 8));
  else img[addr] |= (0x80 >> (X % 8));
}

static void test_small() {
  auto frame = random_frame(SMALL_FRAME_STRIDE * SMALL_H, 1);
  // Padding bits of each row must be ignored by the mapping.
  std::vector<uint8_t> ref(SMALL_RAM_BYTES, 0);
  for (int y = 0; y < SMALL_H; ++y)
    for (int x = 0; x < SMALL_W; ++x)
      elecrow_small_point(ref.data(), x, y, get_pixel(frame.data(), SMALL_FRAME_STRIDE, x, y));
  std::vector<uint8_t> ram(SMALL_RAM_BYTES, 0xAA);
  map_small(frame.data(), ram.data());
  CHECK(std::memcmp(ref.data(), ram.data(), SMALL_RAM_BYTES) == 0, "small mapping differs");
}

static void test_wide() {
  auto frame = random_frame(WIDE_FRAME_STRIDE * WIDE_H, 2);
  std::vector<uint8_t> ref(WIDE_MEM_BYTES, 0xFF);  // Paint_Clear(WHITE)
  for (int y = 0; y < WIDE_H; ++y)
    for (int x = 0; x < WIDE_W; ++x)
      elecrow_wide_point(ref.data(), x, y, get_pixel(frame.data(), WIDE_FRAME_STRIDE, x, y));
  std::vector<uint8_t> mem(WIDE_MEM_BYTES, 0x55);
  map_wide(frame.data(), mem.data());
  for (size_t i = 0; i < WIDE_MEM_BYTES; ++i) {
    if (static_cast<uint8_t>(~ref[i]) != mem[i]) {
      CHECK(false, "wide mapping differs at byte %zu", i);
      break;
    }
  }
  // Streaming order of EPD_Display: templine inner, tempcol outer; the slave
  // continues at tempcol 50.
  size_t tempcol = 0, templine = 0;
  for (int half = 0; half < 2; ++half) {
    for (size_t k = 0; k < WIDE_HALF_BYTES; ++k) {
      uint8_t expect = mem[templine * 100 + tempcol];
      if (wide_stream_byte(mem.data(), half == 1, k) != expect) {
        CHECK(false, "stream order differs (half %d, k %zu)", half, k);
        return;
      }
      if (++templine >= 272) {
        ++tempcol;
        templine = 0;
      }
    }
  }
}

static void test_wide_seam() {
  // A single black pixel at logical x = 395 and x = 396 lands on either side
  // of the 8-column gap.
  std::vector<uint8_t> frame(WIDE_FRAME_STRIDE * WIDE_H, 0);
  set_pixel(frame.data(), WIDE_FRAME_STRIDE, 395, 0, true);
  set_pixel(frame.data(), WIDE_FRAME_STRIDE, 396, 0, true);
  std::vector<uint8_t> mem(WIDE_MEM_BYTES);
  map_wide(frame.data(), mem.data());
  int found = 0;
  for (int x = 0; x < WIDE_MEM_W; ++x) {
    if (mem[271 * WIDE_MEM_STRIDE + x / 8] & (0x80 >> (x % 8))) {
      CHECK(x == 800 - 1 - 395 || x == 800 - 1 - 404, "unexpected seam column %d", x);
      ++found;
    }
  }
  CHECK(found == 2, "seam pixels found: %d", found);
}

static void test_marker() {
  std::vector<uint8_t> frame(SMALL_FRAME_STRIDE * SMALL_H, 0);
  Rect r = draw_offline_marker(frame.data(), SMALL_W, SMALL_H, 1);
  CHECK(r.x0 == 0 && r.y1 == SMALL_H - 1, "marker not at bottom-left");
  CHECK(r.x1 < SMALL_W && r.y0 >= 0, "marker out of bounds");
  CHECK(get_pixel(frame.data(), SMALL_FRAME_STRIDE, r.x0, r.y0), "border missing");
  int black = 0;
  for (int y = r.y0 + 1; y < r.y1; ++y)
    for (int x = r.x0 + 1; x < r.x1; ++x) black += get_pixel(frame.data(), SMALL_FRAME_STRIDE, x, y);
  CHECK(black > 50, "marker text missing (%d)", black);
  std::vector<uint8_t> wide(WIDE_FRAME_STRIDE * WIDE_H, 0xFF);
  Rect w = draw_offline_marker(wide.data(), WIDE_W, WIDE_H, 2);
  CHECK(!get_pixel(wide.data(), WIDE_FRAME_STRIDE, w.x0 + 1, w.y0 + 1), "box not cleared");
}

int main() {
  test_small();
  test_wide();
  test_wide_seam();
  test_marker();
  if (failures) {
    std::printf("%d failure(s)\n", failures);
    return 1;
  }
  std::printf("frame_map: all tests passed\n");
  return 0;
}
