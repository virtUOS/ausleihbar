# E-ink door displays (desksharing) — deployment guide

Battery-powered e-ink door signs for desksharing rooms (design: ADR-0022,
`docs/superpowers/specs/2026-11-19-door-displays-design.md`). The server
renders every frame; the device only shows it and reports button presses.
Firmware build details:
[`firmware/door-display/README.md`](../firmware/door-display/README.md)
(not repeated here). Privacy summary: `docs/desksharing-personalrat.md` §10.

## 1. What you need
- Elecrow CrowPanel ESP32-S3 e-paper boards: **2.1"** (single offices) and
  **5.79"** (meeting rooms, multi-desk offices).
- A department with desksharing enabled (INSTALL §6.2) and rooms set up in the
  "Plätze" workspace. A display belongs to the room's department.
- Nothing new on the server: no service, no environment variable, no cron job
  (`desks_tick` / `desks_daily` of §6.2 already apply; `desks_daily` also
  deletes old display event rows).

## 2. Network prerequisites
- The displays are pure HTTPS clients (no open port, Bluetooth off). They must
  reach the production host on **TCP 443** — nothing else. Recommended: a
  separate device Wi-Fi/VLAN that allows only DNS and 443 to the Ausleihbar
  server. No eduroam / WPA2-Enterprise support yet (Wi-Fi SSID and password are
  compiled in).
- The endpoints `/api/displays/frame/` and `/api/displays/event/` must be
  reachable from that network (there is no separate pairing endpoint: an
  unknown device is registered by its first frame request). Caddy needs no
  special configuration.
- Frame requests from unknown/unpaired devices are throttled **per client IP
  (12 requests/min)** using `common.net.client_ip`, i.e. the last
  `X-Forwarded-For` entry set by Caddy. One IP may register at most 10 new
  (pending) displays per 10 minutes; paired displays are limited to 60 frame
  requests/min each (429 with `Retry-After`).
  Keep the proxy setup as in INSTALL §7 (backend reachable only through Caddy);
  behind an extra load balancer or NAT all displays share one bucket.
- Certificates: the firmware validates the server chain against the bundled
  roots **ISRG Root X1 and X2** (Let's Encrypt, Caddy's default). If the
  server's chain ends in another CA, add its PEM to
  `firmware/door-display/src/root_ca.h` and reflash every display (see the
  firmware README). Certificate dates are not checked (the device has no
  clock).

## 3. Flashing (per panel)
1. Copy `firmware/door-display/secrets.ini.example` to `secrets.ini`
   (git-ignored): Wi-Fi SSID/password and `server_url = https://<host>`. They
   are compiled in; changing them means reflashing.
2. Build and flash with PlatformIO over USB (works even in deep sleep):
   `pio run -e small_jd -t upload` (2.1"), `-e wide` (5.79").
3. **2.1" boards exist with two display controllers.** The boards tested so
   far (2026-11) have the JD79661: env `small_jd`. `small` is for the SSD1680
   variant; on a JD79661 board it leaves the panel blank (serial log
   `draw full FAILED`) — then flash `small_jd`.
4. **USB on macOS** (the flashing computer, not the server):
   - Confirm macOS's "Allow accessory to connect?" prompt when plugging a
     board in. Without it the board only gets power, no data.
   - The 5.79" uses a CH340 (`1a86:7523`); macOS's own driver handles it
     (`/dev/cu.usbserial-*`).
   - The 2.1" uses a **CH340K (`1a86:7522`) that macOS has no driver for**:
     install WCH's *CH34xVCPDriver* (Homebrew cask or Mac App Store), open
     the app once, then enable it under *System Settings → General → Login
     Items & Extensions → Driver Extensions* and replug the board. No reboot
     needed; the port is `/dev/cu.wchusbserial*`.
   - If no port appears, `ioreg -p IOUSB` still lists the board as
     "USB Serial". A "Google Chrome" client below it only means no driver
     took the device (Chrome attaches to every unclaimed USB device) — it is
     a symptom, not the cause.
5. Plain HTTP is only possible in dev builds (`-DDOOR_DEV_INSECURE=1`); never
   for production.

## 4. Pairing
1. Power the display. It shows an **8-character pairing code** (valid 10
   minutes). Power displays only when you are about to pair them: an unpaired
   display polls the server **every 30 s**.
2. In the app: *Administration → Verbindungen → Türschilder*
   (`/admin/displays`), enter the code, pick the target (a room or an item,
   see §4a), optionally a name. The display shows it within about a minute.
   `/desks/manage/displays` redirects there.
3. Only **app admins** can pair, rename, reassign and revoke (ADR-0023,
   amends ADR-0022). Department admins (pool lenders) keep the room preview. The page also shows last contact and firmware
   per display. A **room preview** (PNG of what the sign would show) works
   without hardware.

### 4a. Item signs
A display can hang at a single **item** (a unit of a self-service product,
ADR-0023) instead of a room; exactly one of room and item is set. Pick the
item in the same pairing dialog (search by inventory number or product). The
sign shows the state **Frei**, **Reserviert**, **Verspätet** (check-in
missed, not yet released), **In Benutzung**, **Geschlossen** or
**Außer Betrieb**, never a name, plus the booking code. A pool without opening
hours counts as open except on its closed weekdays; a block on the item itself
shows "Außer Betrieb"; retiring the item unpairs the display. The buttons only
refresh the image. Check-in happens on the phone via the item's QR sticker
(`/r/<qr_id>`).

## 5. Mounting
- Mount the sign at the door so the **USB port is not reachable** (housing,
  adhesive cover). The device secret sits unencrypted in NVS: whoever reads
  the flash over USB can impersonate the display for its room (and only that
  room). Flash encryption and secure boot come with a later setup mode — never
  enabled on test boards (eFuses are irreversible).
- Place the QR code readable for phones; the sign shows a QR only when
  something is bookable.

## 6. Operation
- **Refresh:** 300 s in business hours; outside until shortly before opening
  (at most 4 h). A button press wakes the display at once. An unchanged state
  is not redrawn, except once an hour: the ETag includes the local hour, so
  "Stand HH:MM" shows the last refresh and is at most about an hour old while
  the sign is healthy in business hours (outside them, up to the 4 h wake).
- **Battery:** the boards have no battery voltage divider on a GPIO, so the
  level cannot be measured; the management page shows "—". Replace/charge on a
  fixed schedule.
- **Revoke / replace:** revoking a display invalidates its secret immediately;
  the device shows the pairing screen again. To replace a broken one, revoke
  it, pair the new board to the same room. A full flash erase (`pio run -t
  erase`) deletes the secret too, requiring a new pairing. Revoking deletes
  the display record: still-running meeting bookings made anonymously at that
  sign lose their door marker and then look like anonymized bookings.
- **Error screens:**
  - *"Keine Verbindung"* box bottom-left — Wi-Fi/network/server error; the
    last image stays, the device retries after 300 s. The "Stand HH:MM" stamp
    shows when the image was last refreshed. Check Wi-Fi, firewall (443),
    certificate chain.
  - **Pairing screen** (code) — not paired, or revoked, or the secret was
    erased.
  - *Silent display* — "last seen" on the management page shows it.
- **Check-in/out at the door:** anyone at the door can check in/out and take a
  free meeting room anonymously ("Spontan belegt"); access groups do not limit
  this. Check-out at the door sends no mail.
