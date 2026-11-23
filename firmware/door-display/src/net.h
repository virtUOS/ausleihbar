// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Wi-Fi and the device API of the server (desksharing.views_display):
//   GET  /api/displays/frame/  -> 200 frame | 304
//   POST /api/displays/event/  {"button": ...} -> 200 frame | 304 | 401
// Both answer 429 when throttled; 200/304 carry ETag, X-Next-Wake and
// X-Session-Timeout.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace net {

constexpr int ERR_NETWORK = -1;    // no Wi-Fi / connection / timeout
constexpr int ERR_BAD_FRAME = -2;  // 200 with a body of the wrong size

struct Response {
  int status = ERR_NETWORK;     // HTTP status or ERR_*
  uint32_t next_wake = 0;       // seconds, 0 = header missing
  uint32_t session_timeout = 0; // seconds the device stays awake for buttons
  uint32_t retry_after = 0;     // seconds (429), 0 = header missing
  char etag[72] = {0};          // as sent by the server (quoted)
  bool has_frame = false;       // body holds exactly FRAME_BYTES
};

bool connect(uint32_t timeout_ms);
void off();

// ``body`` must hold FRAME_BYTES; ``etag`` may be empty.
Response get_frame(const char *secret, const char *etag, uint8_t *body);
Response post_event(const char *secret, const char *button, const char *etag, uint8_t *body);

}  // namespace net
