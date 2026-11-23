// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)
//
// Elecrow CrowPanel ESP32-S3 2.13" e-paper HMI display (DIE01021S), 122x250
// black/white, used landscape as 250x122.
//
// Sources (checked 2026-11-23):
//  - Pin table + controller list: Elecrow's repository README "Pin definition"
//    https://github.com/Elecrow-RD/CrowPanel-ESP32-2.13-E-paper-HMI-Display-with-122-250
//  - EPD pins / power pin / buttons: example code and factory source, same repo
//    (example/arduino/Example Code/2.13_partial_refresh/spi.h,
//     factory_soucecode/2.1.3_tow/main/main.ino: pinMode(7) "screen power",
//     HOME_KEY 2, EXIT_KEY 1, PRV_KEY 6, NEXT_KEY 4, OK_KEY 5)
//  - Schematic (Eagle_SCH&PCB/CrowPanel ESP32 Display-2.13(E) Inch(1).sch):
//    nets IO2_MENU, IO1_EXIT, IO6_UP, IO4_DOWN, IO5_CONF each 4.7k pull-up to
//    3V3, key to GND (active low); IO7_LCD_3.3_CTL drives the gate of a 2N7002
//    low-side switch of the panel ground (high = panel powered); IO19_LED
//    via 4.7k to a red LED to GND (active high). BAT only reaches the charger
//    and the power path: no battery voltage divider on any GPIO.
//  - Wiki: https://www.elecrow.com/wiki/CrowPanel_ESP32_E-Paper_HMI_2.13-inch_Display.html
#pragma once

#define BOARD_PANEL_ID "2.1"  // X-Panel value expected by the server

// Logical (server) frame: landscape 250x122.
#define FRAME_WIDTH 250
#define FRAME_HEIGHT 122

// E-paper SPI (write-only, 4-wire).
#define PIN_EPD_SCK 12
#define PIN_EPD_MOSI 11
#define PIN_EPD_CS 14
#define PIN_EPD_DC 13
#define PIN_EPD_RST 10
#define PIN_EPD_BUSY 9
#define PIN_EPD_POWER 7  // high = panel powered (low-side switch)

#define PIN_LED 19  // red LED, active high
#define LED_ACTIVE_HIGH 1

// Buttons on the right edge, all active low with external pull-ups.
// Top/bottom follow the PCB layout (K3 = MENU at the upper end, K4 = EXIT at
// the lower end of the key edge, .brd coordinates).
// TODO(verify on hardware): which key is physically "top" and which rocker
// direction is "up" in the mounted landscape orientation of the frame.
#define PIN_BTN_TOP 2     // MENU
#define PIN_BTN_UP 6      // rocker up
#define PIN_BTN_DOWN 4    // rocker down
#define PIN_BTN_PRESS 5   // rocker press (CONF)
#define PIN_BTN_BOTTOM 1  // EXIT

#define BOARD_HAS_BATTERY_ADC 0

// 2.13" board revisions ship with either an SSD1680 (factory firmware and
// "Example Code") or a JD79661 (example/arduino-v1.2). Select with the env
// (small / small_jd).
// TODO(verify on hardware): which controller the user's board has.
#ifndef SMALL_CONTROLLER_JD79661
#define SMALL_CONTROLLER_JD79661 0
#endif
