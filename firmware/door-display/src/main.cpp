// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Door display firmware: the server renders every frame, the device only
// shows it. One wake cycle:
//   wake (timer or key) -> Wi-Fi -> GET frame / POST key event -> draw
//   -> while the server keeps a session open: poll keys, POST each press
//   -> deep sleep for X-Next-Wake seconds (keys wake it early).
#include <Arduino.h>
#include <esp_sleep.h>
#include <string.h>

#include "board.h"
#include "buttons.h"
#include "frame_map.h"
#include "net.h"
#include "panel.h"
#include "state.h"

#ifndef DOOR_DEBUG
#define DOOR_DEBUG 0
#endif

namespace {

constexpr uint32_t WIFI_TIMEOUT_MS = 15000;
constexpr uint32_t OFFLINE_RETRY_S = 300;
constexpr uint32_t THROTTLED_RETRY_S = 60;
constexpr uint32_t DEFAULT_WAKE_S = 300;
constexpr uint32_t MAX_WAKE_S = 7 * 24 * 3600;
constexpr uint32_t MAX_SESSION_S = 120;
constexpr uint32_t KEY_RELEASE_WAIT_MS = 3000;

uint8_t *body = nullptr;     // frame received from the server
uint8_t *scratch = nullptr;  // marker composition

uint8_t *alloc_frame() {
  auto *p = static_cast<uint8_t *>(ps_malloc(FRAME_BYTES));
  return p ? p : static_cast<uint8_t *>(malloc(FRAME_BYTES));
}

void log_line(const char *fmt, ...) {
  char line[160];
  va_list args;
  va_start(args, fmt);
  vsnprintf(line, sizeof line, fmt, args);
  va_end(args);
  Serial.println(line);
}

// Draws a received frame. Partial refresh only inside a key session, when the
// panel content is known and not on every 10th draw.
void draw(const uint8_t *frame, bool session) {
  const uint8_t *old = state::shown_frame();
  bool partial = session && old && panel::supports_partial() && !state::next_draw_must_be_full();
  bool ok = partial ? panel::show_partial(frame, old) : panel::show_full(frame);
  state::count_draw();
  log_line("draw %s %s", partial ? "partial" : "full", ok ? "ok" : "FAILED");
  state::set_shown_frame(ok ? frame : nullptr);
  state::set_offline_marker_shown(false);
}

// Keeps the image and adds a small "Keine Verbindung" box bottom-left.
void draw_offline_marker() {
  if (state::offline_marker_shown()) return;
  const int scale = FRAME_WIDTH > 400 ? 2 : 1;
  const uint8_t *old = state::shown_frame();
  bool ok;
  if (old) {
    memcpy(scratch, old, FRAME_BYTES);
    frame_map::draw_offline_marker(scratch, FRAME_WIDTH, FRAME_HEIGHT, scale);
    ok = panel::show_partial(scratch, old);  // full where partial is unsupported
    state::set_shown_frame(ok ? scratch : nullptr);
  } else if (panel::supports_partial()) {
    // Content unknown (e.g. after deep sleep on the 5.79"): identical old/new
    // RAM outside the box leaves those pixels alone; inside the box old is
    // the inverse of new, so every box pixel is driven.
    memset(scratch, 0, FRAME_BYTES);
    frame_map::Rect r = frame_map::draw_offline_marker(scratch, FRAME_WIDTH, FRAME_HEIGHT, scale);
    memcpy(body, scratch, FRAME_BYTES);
    for (int y = r.y0; y <= r.y1; ++y) {
      for (int x = r.x0; x <= r.x1; ++x) {
        bool black = frame_map::get_pixel(scratch, FRAME_STRIDE, x, y);
        frame_map::set_pixel(body, FRAME_STRIDE, x, y, !black);
      }
    }
    ok = panel::show_partial(scratch, body);
    state::set_shown_frame(nullptr);
  } else {
    memset(scratch, 0, FRAME_BYTES);
    frame_map::draw_offline_marker(scratch, FRAME_WIDTH, FRAME_HEIGHT, scale);
    ok = panel::show_full(scratch);
    state::set_shown_frame(ok ? scratch : nullptr);
  }
  log_line("offline marker %s", ok ? "ok" : "FAILED");
  state::set_offline_marker_shown(ok);
  // The next successful fetch must redraw (else a 304 would keep the marker).
  state::clear_etag();
}

[[noreturn]] void sleep_for(uint32_t seconds) {
  if (seconds == 0) seconds = DEFAULT_WAKE_S;
  if (seconds > MAX_WAKE_S) seconds = MAX_WAKE_S;
  panel::off();
  net::off();
  uint64_t keys = buttons::wait_release(KEY_RELEASE_WAIT_MS);
  log_line("sleep %lu s", static_cast<unsigned long>(seconds));
  Serial.flush();
#if LED_ACTIVE_HIGH
  digitalWrite(PIN_LED, LOW);
#else
  digitalWrite(PIN_LED, HIGH);
#endif
  esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(seconds) * 1000000ULL);
  if (keys) esp_sleep_enable_ext1_wakeup(keys, ESP_EXT1_WAKEUP_ANY_LOW);
  esp_deep_sleep_start();
}

// Handles one server answer. Returns false when the device should go to
// sleep for ``*sleep_s`` right away (error / throttled).
bool apply(const net::Response &r, bool session, uint32_t *sleep_s) {
  log_line("http %d wake=%lu session=%lu", r.status, static_cast<unsigned long>(r.next_wake),
      static_cast<unsigned long>(r.session_timeout));
  if (r.status == 200 && r.has_frame) {
    draw(body, session);
    // Remember the ETag only when the panel really shows this frame.
    if (state::shown_frame()) {
      state::set_etag(r.etag);
    } else {
      state::clear_etag();
    }
    *sleep_s = r.next_wake;
    return true;
  }
  if (r.status == 304) {  // unchanged (never after a marker: its ETag was cleared)
    *sleep_s = r.next_wake;
    return true;
  }
  if (r.status == 429) {
    *sleep_s = r.retry_after ? r.retry_after : THROTTLED_RETRY_S;
    return false;
  }
  draw_offline_marker();  // network error, 5xx, unexpected status, bad frame
  *sleep_s = OFFLINE_RETRY_S;
  return false;
}

net::Response send_key(buttons::Button key) {
  net::Response r = net::post_event(state::secret(), buttons::name(key), state::etag(), body);
  if (r.status == 401) {
    // Unknown or revoked secret: the frame endpoint shows the pairing screen.
    r = net::get_frame(state::secret(), state::etag(), body);
  }
  return r;
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LED_ACTIVE_HIGH ? LOW : HIGH);
  btStop();
  state::begin();
  buttons::begin();
  body = alloc_frame();
  scratch = alloc_frame();
  if (!body || !scratch) sleep_for(OFFLINE_RETRY_S);

  buttons::Button woke_by = buttons::from_wakeup();
  log_line("%s, wake cause %d, key %s", FIRMWARE_VERSION, esp_sleep_get_wakeup_cause(),
      woke_by == buttons::NONE ? "-" : buttons::name(woke_by));

  if (!net::connect(WIFI_TIMEOUT_MS)) {
    log_line("wifi failed");
    draw_offline_marker();
    sleep_for(OFFLINE_RETRY_S);
  }
#if DOOR_DEBUG
  char fp[7];
  state::secret_fingerprint(fp);
  log_line("secret %s…", fp);
#endif

  uint32_t sleep_s = DEFAULT_WAKE_S;
  net::Response r = woke_by == buttons::NONE
                        ? net::get_frame(state::secret(), state::etag(), body)
                        : send_key(woke_by);
  if (!apply(r, woke_by != buttons::NONE, &sleep_s)) sleep_for(sleep_s);

  // Key session: stay awake while the server keeps one open.
  uint32_t session = r.session_timeout;
  while (session > 0) {
    if (session > MAX_SESSION_S) session = MAX_SESSION_S;
    buttons::Button key = buttons::wait_press(session * 1000);
    if (key == buttons::NONE) {
      // Timed out on the device: fetch the normal view the server returns now.
      r = net::get_frame(state::secret(), state::etag(), body);
      if (!apply(r, true, &sleep_s)) sleep_for(sleep_s);
      break;
    }
    log_line("key %s", buttons::name(key));
    r = send_key(key);
    if (!apply(r, true, &sleep_s)) sleep_for(sleep_s);
    session = r.session_timeout;
  }
  sleep_for(sleep_s);
}

void loop() {}  // never reached: setup() ends in deep sleep
