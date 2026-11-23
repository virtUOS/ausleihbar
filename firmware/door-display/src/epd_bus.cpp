// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
#include "epd_bus.h"

#include <Arduino.h>
#include <SPI.h>
#include <driver/gpio.h>

#include "board.h"

namespace epd_bus {

namespace {
// Elecrow's examples bit-bang the bus; SSD1680/SSD1683 accept up to 20 MHz
// writes. 4 MHz keeps margin on the flex cable.
constexpr uint32_t SPI_HZ = 4000000;
SPIClass spi(FSPI);
const SPISettings settings(SPI_HZ, MSBFIRST, SPI_MODE0);
bool spi_up = false;
bool is_powered = false;
}  // namespace

void power_on() {
  gpio_hold_dis(static_cast<gpio_num_t>(PIN_EPD_POWER));
  pinMode(PIN_EPD_POWER, OUTPUT);
  digitalWrite(PIN_EPD_POWER, HIGH);
  pinMode(PIN_EPD_CS, OUTPUT);
  digitalWrite(PIN_EPD_CS, HIGH);
  pinMode(PIN_EPD_DC, OUTPUT);
  pinMode(PIN_EPD_RST, OUTPUT);
  digitalWrite(PIN_EPD_RST, HIGH);
  pinMode(PIN_EPD_BUSY, INPUT);
  if (!spi_up) {
    spi.begin(PIN_EPD_SCK, -1, PIN_EPD_MOSI, -1);
    spi_up = true;
  }
  delay(10);  // let the panel supply settle
  is_powered = true;
}

bool powered() { return is_powered; }

void power_off() {
  if (spi_up) {
    spi.end();
    spi_up = false;
  }
  // High-Z signal lines: the panel's ground is switched off, a driven line
  // would feed it through its input protection.
  for (int pin : {PIN_EPD_SCK, PIN_EPD_MOSI, PIN_EPD_CS, PIN_EPD_DC, PIN_EPD_RST}) {
    pinMode(pin, INPUT);
  }
  pinMode(PIN_EPD_POWER, OUTPUT);
  digitalWrite(PIN_EPD_POWER, LOW);
  // The 2N7002 gate has no pull-down on the schematic: keep it low in sleep.
  gpio_hold_en(static_cast<gpio_num_t>(PIN_EPD_POWER));
  is_powered = false;
}

void reset(uint32_t low_ms, uint32_t settle_ms) {
  digitalWrite(PIN_EPD_RST, HIGH);
  delay(settle_ms);
  digitalWrite(PIN_EPD_RST, LOW);
  delay(low_ms);
  digitalWrite(PIN_EPD_RST, HIGH);
  delay(settle_ms);
}

void command(uint8_t cmd) {
  spi.beginTransaction(settings);
  digitalWrite(PIN_EPD_DC, LOW);
  digitalWrite(PIN_EPD_CS, LOW);
  spi.transfer(cmd);
  digitalWrite(PIN_EPD_CS, HIGH);
  digitalWrite(PIN_EPD_DC, HIGH);
  spi.endTransaction();
}

void begin_data() {
  spi.beginTransaction(settings);
  digitalWrite(PIN_EPD_DC, HIGH);
  digitalWrite(PIN_EPD_CS, LOW);
}

void write_byte(uint8_t value) { spi.transfer(value); }

void end_data() {
  digitalWrite(PIN_EPD_CS, HIGH);
  spi.endTransaction();
}

void data(uint8_t value) {
  begin_data();
  write_byte(value);
  end_data();
}

void data(const uint8_t *values, size_t len) {
  begin_data();
  for (size_t i = 0; i < len; ++i) write_byte(values[i]);
  end_data();
}

void command_data(uint8_t cmd, const uint8_t *values, size_t len) {
  command(cmd);
  data(values, len);
}

bool wait_idle(int busy_level, uint32_t timeout_ms) {
  delay(1);
  uint32_t start = millis();
  while (digitalRead(PIN_EPD_BUSY) == busy_level) {
    if (millis() - start > timeout_ms) return false;
    delay(2);
  }
  return true;
}

}  // namespace epd_bus
