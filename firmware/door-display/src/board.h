// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
#pragma once

#if defined(BOARD_SMALL)
#include "board_small.h"
#elif defined(BOARD_WIDE)
#include "board_wide.h"
#else
#error "Build with -DBOARD_SMALL=1 or -DBOARD_WIDE=1 (pio run -e small|wide)"
#endif

#include <stddef.h>

// Server frame: row-major, MSB = leftmost pixel, bit 1 = black.
constexpr size_t FRAME_STRIDE = (FRAME_WIDTH + 7) / 8;
constexpr size_t FRAME_BYTES = FRAME_STRIDE * FRAME_HEIGHT;
