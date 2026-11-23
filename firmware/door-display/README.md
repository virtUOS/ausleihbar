# Door display firmware

Firmware for the e-ink door signs of the desksharing area
(Elecrow CrowPanel ESP32-S3 e-paper boards). The server renders every frame;
the device is a thin HTTPS client:

wake (timer or key) → Wi-Fi → `GET /api/displays/frame/` or
`POST /api/displays/event/` → draw → while the server keeps a key session
open (`X-Session-Timeout`), poll the keys and post every press → deep sleep
for `X-Next-Wake` seconds (any key wakes it early).

| Env        | Panel                         | Controller        |
|------------|-------------------------------|-------------------|
| `small`    | 2.13" (sent as `X-Panel: 2.1`) | SSD1680           |
| `small_jd` | 2.13", later board revision   | JD79661           |
| `wide`     | 5.79"                         | 2 × SSD1683       |

Elecrow ships the 2.13" board with either controller. If `small` leaves the
panel blank (the serial log shows `draw full FAILED`), flash `small_jd`.

## Setup

PlatformIO Core (CLI) or the PlatformIO IDE extension. Without a global
install:

```bash
python3 -m venv .venv && .venv/bin/pip install platformio
alias pio="$PWD/.venv/bin/pio"
```

Copy `secrets.ini.example` to `secrets.ini` (git-ignored) and fill in the
Wi-Fi credentials and the server base URL. Without `secrets.ini` the build
uses placeholder values (it compiles, but the device cannot connect).

## Build, flash, monitor

```bash
cd firmware/door-display
pio run -e small                     # or wide / small_jd
pio run -e small -t upload           # board on USB (CH340, /dev/cu.usbserial-*)
pio device monitor                   # 115200 baud
```

The CH340 USB-serial chip resets the ESP32 for flashing, also while it is in
deep sleep. A full erase (`pio run -t erase`) also deletes the device secret:
the display then has to be paired again.

## Bench setup against the dev backend

Plain HTTP is only accepted with `-DDOOR_DEV_INSECURE=1` (the build fails
otherwise). In `secrets.ini`:

```ini
[secrets]
wifi_ssid = my-wifi
wifi_pass = my-password
server_url = http://<mac-ip>:8001
dev_flags = -DDOOR_DEV_INSECURE=1 -DDOOR_DEBUG=1
```

`DOOR_DEBUG` adds the first 6 hex characters of the device secret to the
serial log (never the secret itself). The device first shows a pairing code;
claim it on the *Türschilder* page
(`/desks/manage/displays`).

## Behaviour

- **Secret:** 32 random bytes (hardware RNG with Wi-Fi on), 64 hex chars,
  stored in NVS (`door/secret`); sent as `Authorization: Bearer …`. NVS is
  not encrypted: whoever can read the flash over USB gets the secret (mount
  the sign so the USB port is out of reach; flash encryption is planned with
  the later setup mode). Revoking the display in the UI invalidates it.
- **TLS:** `WiFiClientSecure` with the Let's Encrypt roots ISRG Root X1
  (RSA chains) and X2 (ECDSA chains, Caddy's default) in `src/root_ca.h`.
  Another CA: append its PEM block there (each line as `"…\n"`) and note its
  SHA-256 fingerprint in the comment. Certificate dates are not checked
  (no clock needed); the TLS handshake times out after 15 s.
- **Refresh:** full refresh for a new frame on a timer wake and on every 10th
  draw; partial refresh for answers to key presses when the current panel
  content is known (2.13": kept in RTC memory across deep sleep; 5.79": only
  within one wake period, so the first key press after sleep costs a full
  refresh). The JD79661 variant always refreshes fully.
- **Errors:** no Wi-Fi, network error, 5xx or a malformed frame keep the
  image, add a small "Keine Verbindung" box bottom-left and retry after
  300 s. `429` sleeps `Retry-After` (10 s–15 min, default 60 s). A `401` on a
  key event fetches the frame (pairing screen).
- **Timing bounds:** `X-Next-Wake` is clamped to 30 s–6 h, the key session
  (`X-Session-Timeout`) to at most 120 s; missing or malformed headers (not
  1–6 ASCII digits) fall back to 300 s / no session.
- **Keys:** top button → `top`, rocker → `up` / `down`, rocker press →
  `top`, bottom button → `bottom`; a wake that cannot be pinned to one key
  is sent as `wake` (refresh only).
- **Sleep:** panel controller to deep sleep, panel power (GPIO 7) off and
  held low, Wi-Fi off, Bluetooth never started; timer + ext1 (any key low).
- **Battery:** the boards have no battery voltage divider on a GPIO, so
  `X-Battery-mV` is not sent.

Pins and their sources are documented in `src/board_small.h` and
`src/board_wide.h`; facts not yet confirmed on real hardware are marked
`TODO(verify on hardware)`.

## Host test

The frame → controller RAM mapping is hardware-free and tested on the host
against a re-implementation of Elecrow's drawing routines:

```bash
cd test/host
c++ -std=c++17 -I../../src test_frame_map.cpp ../../src/frame_map.cpp -o test_frame_map
./test_frame_map
```
