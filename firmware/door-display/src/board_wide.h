// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Elecrow CrowPanel ESP32-S3 5.79" e-paper HMI display (DIS08792E), 792x272
// black/white, driven by two cascaded SSD1683 (master + slave, 396 columns
// each, an 8-column gap between them in controller RAM).
//
// Sources (checked 2026-11-23):
//  - EPD pins: example code spi.h ("项目板子" = board pins)
//    https://github.com/Elecrow-RD/CrowPanel-ESP32-5.79-E-paper-HMI-Display-with-272-792
//    (example/arduino/Examples/5.79_PWR/spi.h)
//  - Power pin 7 and keys: example/arduino/Examples/5.79_key/5.79_key.ino
//    (HOME_KEY 2, EXIT_KEY 1, PRV_KEY 6, NEXT_KEY 4, OK_KEY 5, pin 7 "screen
//    power"); wiki pin table
//    https://www.elecrow.com/wiki/CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display.html
//  - Schematic (Eagle_SCH&PCB/.../CrowPanel ESP32 Display-5.79(E) Inch.sch):
//    nets IO45_CS, IO46_D/C, IO47_RES, IO48_BUSY; IO2_MENU, IO1_EXIT, IO6_UP,
//    IO4_DOWN, IO5_CONF each 4.7k pull-up to 3V3, key to GND (active low);
//    IO7_LCD_3.3_CTL -> 100k -> gate of a 2N7002 switching the panel ground
//    (high = panel powered); IO41_LED via 4.7k to the LED. BAT only reaches
//    the charger and power path: no battery voltage divider on any GPIO.
#pragma once

#define BOARD_PANEL_ID "5.79"

#define FRAME_WIDTH 792
#define FRAME_HEIGHT 272

#define PIN_EPD_SCK 12
#define PIN_EPD_MOSI 11
#define PIN_EPD_CS 45
#define PIN_EPD_DC 46
#define PIN_EPD_RST 47
#define PIN_EPD_BUSY 48
#define PIN_EPD_POWER 7

// TODO(verify on hardware): LED polarity (schematic shows IO41 -> 4.7k -> LED,
// same circuit as the 2.13" board, so active high is assumed).
#define PIN_LED 41
#define LED_ACTIVE_HIGH 1

// Verified on hardware: top/bottom keys and rocker direction in the mounted
// orientation (PCB: K3 = MENU upper, K4 = EXIT lower end).
#define PIN_BTN_TOP 2
#define PIN_BTN_UP 6
#define PIN_BTN_DOWN 4
#define PIN_BTN_PRESS 5
#define PIN_BTN_BOTTOM 1

#define BOARD_HAS_BATTERY_ADC 0
