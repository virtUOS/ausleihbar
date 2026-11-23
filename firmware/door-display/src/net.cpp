// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
#include "net.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <string.h>

#include "board.h"
#include "root_ca.h"

#ifndef DOOR_DEV_INSECURE
#define DOOR_DEV_INSECURE 0
#endif

namespace {

constexpr bool starts_with(const char *s, const char *prefix) {
  return *prefix == '\0' || (*s == *prefix && starts_with(s + 1, prefix + 1));
}

static_assert(starts_with(SERVER_URL, "https://") ||
                  (DOOR_DEV_INSECURE && starts_with(SERVER_URL, "http://")),
              "SERVER_URL must start with https:// (http:// only with -DDOOR_DEV_INSECURE=1)");

constexpr bool PLAIN_HTTP = starts_with(SERVER_URL, "http://");

WiFiClient plain_client;
WiFiClientSecure tls_client;
HTTPClient http;
bool clients_ready = false;

const char *HEADER_KEYS[] = {"ETag", "X-Next-Wake", "X-Session-Timeout", "Retry-After"};

// Collects the response body into a fixed buffer (handles chunked bodies via
// HTTPClient::writeToStream).
class BufferStream : public Stream {
 public:
  BufferStream(uint8_t *buf, size_t cap) : buf_(buf), cap_(cap) {}
  size_t write(uint8_t b) override { return write(&b, 1); }
  size_t write(const uint8_t *data, size_t len) override {
    if (len_ + len > cap_) {
      overflow_ = true;
      size_t room = cap_ - len_;
      memcpy(buf_ + len_, data, room);
      len_ = cap_;
      return len;  // keep draining the connection
    }
    memcpy(buf_ + len_, data, len);
    len_ += len;
    return len;
  }
  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  void flush() override {}
  size_t length() const { return len_; }
  bool overflow() const { return overflow_; }

 private:
  uint8_t *buf_;
  size_t cap_;
  size_t len_ = 0;
  bool overflow_ = false;
};

uint32_t header_u32(const char *name) {
  String value = http.header(name);
  value.trim();
  if (value.isEmpty()) return 0;
  for (size_t i = 0; i < value.length(); ++i) {
    if (!isDigit(value[i])) return 0;
  }
  return static_cast<uint32_t>(value.toInt());
}

void setup_clients() {
  if (clients_ready) return;
#if DOOR_DEV_INSECURE
  tls_client.setInsecure();  // bench only: no certificate check
#else
  tls_client.setCACert(ROOT_CA_PEM);
#endif
  http.setReuse(true);
  http.setConnectTimeout(8000);
  http.setTimeout(10000);
  http.setUserAgent(FIRMWARE_VERSION);
  http.collectHeaders(HEADER_KEYS, sizeof(HEADER_KEYS) / sizeof(HEADER_KEYS[0]));
  clients_ready = true;
}

bool begin(const char *path) {
  setup_clients();
  String url = String(SERVER_URL) + path;
  if (PLAIN_HTTP) return http.begin(plain_client, url);
  return http.begin(tls_client, url);
}

void add_headers(const char *secret, const char *etag) {
  http.addHeader("Authorization", String("Bearer ") + secret);
  http.addHeader("X-Panel", BOARD_PANEL_ID);
  http.addHeader("X-Firmware", FIRMWARE_VERSION);
#if BOARD_HAS_BATTERY_ADC
  http.addHeader("X-Battery-mV", String(board_battery_mv()));
#endif
  if (etag && etag[0]) http.addHeader("If-None-Match", etag);
}

net::Response finish(int code, uint8_t *body) {
  net::Response r;
  if (code <= 0) {
    http.end();
    r.status = net::ERR_NETWORK;
    return r;
  }
  r.status = code;
  r.next_wake = header_u32("X-Next-Wake");
  r.session_timeout = header_u32("X-Session-Timeout");
  r.retry_after = header_u32("Retry-After");
  String etag = http.header("ETag");
  strncpy(r.etag, etag.c_str(), sizeof(r.etag) - 1);
  if (code == HTTP_CODE_OK) {
    BufferStream sink(body, FRAME_BYTES);
    int written = http.writeToStream(&sink);
    if (written < 0) {
      r.status = net::ERR_NETWORK;
    } else if (sink.overflow() || sink.length() != FRAME_BYTES) {
      r.status = net::ERR_BAD_FRAME;
    } else {
      r.has_frame = true;
    }
  }
  http.end();  // with setReuse(true) the connection stays open when possible
  return r;
}

}  // namespace

namespace net {

bool connect(uint32_t timeout_ms) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > timeout_ms) return false;
    delay(50);
  }
  return true;
}

void off() {
  http.end();
  WiFi.disconnect(true, false);
  WiFi.mode(WIFI_OFF);
}

Response get_frame(const char *secret, const char *etag, uint8_t *body) {
  if (WiFi.status() != WL_CONNECTED || !begin("/api/displays/frame/")) return Response{};
  add_headers(secret, etag);
  return finish(http.GET(), body);
}

Response post_event(const char *secret, const char *button, const char *etag, uint8_t *body) {
  if (WiFi.status() != WL_CONNECTED || !begin("/api/displays/event/")) return Response{};
  add_headers(secret, etag);
  http.addHeader("Content-Type", "application/json");
  String payload = String("{\"button\":\"") + button + "\"}";
  return finish(http.POST(payload), body);
}

}  // namespace net
