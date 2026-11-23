// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
#include "state.h"

#include <Arduino.h>
#include <Preferences.h>
#include <esp_random.h>
#include <esp_sleep.h>
#include <string.h>

#include "board.h"

namespace state {

namespace {

constexpr uint32_t MAGIC = 0xD00D0001;
constexpr size_t SECRET_BYTES = 32;
constexpr size_t SECRET_HEX = SECRET_BYTES * 2;

struct Rtc {
  uint32_t magic;
  char etag[72];
  uint32_t draws;
  bool frame_valid;
  bool marker_shown;
};

RTC_DATA_ATTR Rtc rtc;
#if defined(BOARD_SMALL)
RTC_DATA_ATTR uint8_t rtc_shown[FRAME_BYTES];
uint8_t *shown_buffer() { return rtc_shown; }
#else
uint8_t *shown = nullptr;  // heap (PSRAM), valid within one wake period only
uint8_t *shown_buffer() { return shown; }
#endif

char secret_buf[SECRET_HEX + 1];

bool valid_secret(const String &s) {
  if (s.length() != SECRET_HEX) return false;
  for (size_t i = 0; i < s.length(); ++i) {
    if (!isHexadecimalDigit(s[i])) return false;
  }
  return true;
}

}  // namespace

void begin() {
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED || rtc.magic != MAGIC) {
    memset(&rtc, 0, sizeof rtc);
    rtc.magic = MAGIC;
  }
#if !defined(BOARD_SMALL)
  rtc.frame_valid = false;  // the heap copy did not survive the sleep
  if (!shown) {
    shown = static_cast<uint8_t *>(ps_malloc(FRAME_BYTES));
    if (!shown) shown = static_cast<uint8_t *>(malloc(FRAME_BYTES));
  }
#endif
}

const char *secret() {
  if (secret_buf[0]) return secret_buf;
  Preferences prefs;
  prefs.begin("door", false);
  String stored = prefs.getString("secret", "");
  if (!valid_secret(stored)) {
    uint8_t raw[SECRET_BYTES];
    esp_fill_random(raw, sizeof raw);
    static const char HEX_DIGITS[] = "0123456789abcdef";
    for (size_t i = 0; i < SECRET_BYTES; ++i) {
      secret_buf[2 * i] = HEX_DIGITS[raw[i] >> 4];
      secret_buf[2 * i + 1] = HEX_DIGITS[raw[i] & 0x0F];
    }
    secret_buf[SECRET_HEX] = '\0';
    memset(raw, 0, sizeof raw);
    prefs.putString("secret", secret_buf);
  } else {
    strncpy(secret_buf, stored.c_str(), SECRET_HEX);
    secret_buf[SECRET_HEX] = '\0';
  }
  prefs.end();
  return secret_buf;
}

void secret_fingerprint(char out[7]) {
  memcpy(out, secret(), 6);
  out[6] = '\0';
}

const char *etag() { return rtc.etag; }

void set_etag(const char *etag) {
  strncpy(rtc.etag, etag ? etag : "", sizeof(rtc.etag) - 1);
  rtc.etag[sizeof(rtc.etag) - 1] = '\0';
}

void clear_etag() { rtc.etag[0] = '\0'; }

bool next_draw_must_be_full() { return rtc.draws % 10 == 0; }

void count_draw() { ++rtc.draws; }

const uint8_t *shown_frame() { return rtc.frame_valid ? shown_buffer() : nullptr; }

void set_shown_frame(const uint8_t *frame) {
  uint8_t *buf = shown_buffer();
  if (frame && buf) {
    if (frame != buf) memcpy(buf, frame, FRAME_BYTES);
    rtc.frame_valid = true;
  } else {
    rtc.frame_valid = false;
  }
}

bool offline_marker_shown() { return rtc.marker_shown; }

void set_offline_marker_shown(bool shown_now) { rtc.marker_shown = shown_now; }

}  // namespace state
