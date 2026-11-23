# 0022. Door displays: the server renders the frames

- **Status:** Accepted
- **Date:** 2026-11-23

## Context
Desksharing rooms get battery-powered e-ink door signs (Elecrow CrowPanel
ESP32-S3, 2.1" and 5.79") that show who is checked in, what is free, and let
people check in/out or take a meeting room at the door (spec
`docs/superpowers/specs/2026-11-19-door-displays-design.md`). The display
logic is non-trivial: place states, the privacy rules (opt-out names), the
"end time only if < 5 h" rule, name shortening, key-driven selection and
confirm flows. A device on battery should wake rarely and stay a thin client.

## Decision
- **The server renders, the device only shows (approach A).** Django renders a
  1-bit frame per display with Pillow (`desksharing.door_render`, state in
  `door_view`); the firmware fetches it, draws it and sleeps. Button presses
  are posted as events and the answer is the next frame. States, privacy and
  texts exist once; layout changes need no reflash; any sign can be previewed
  as PNG without hardware (`/api/desks/manage/rooms/<id>/door-preview.png`).
- **Public viewer.** Frames are built with `viewer=None`
  (`desksharing.privacy`): hidden desk holders appear as "belegt", meeting
  rooms show holder and title as everywhere in desksharing.
- **Wake schedule decided by the server** (`X-Next-Wake`): 300 s in business
  hours, otherwise until shortly before opening (at most 4 h). The ETag is
  computed over the frame *without* the "Stand HH:MM" stamp, so an unchanged
  state answers 304 and the panel is not redrawn.
- **Server-side key sessions.** A selection/confirm/duration flow lives in
  `Display.ui_state` (`door_session`), expires after 20 s / 10 s; the device
  stays awake only while the server sends `X-Session-Timeout`.
- **Door actions are anonymous.** Check-in/out and anonymous meeting booking
  act as the display, never as a person: no holder check, **access groups do
  not limit them**, check-out sends no mail. The anonymous booking has
  `holder=None` and `Reservation.display`, so it counts as used in the
  statistics and is not mistaken for an anonymized reservation; a check-out at
  the door releases with `ReleaseReason.DISPLAY`. `DisplayEvent` is the audit
  log (action, room, place, time; **no person**), deleted with the department's
  retention. Desks are only ever booked for a person (QR code, login).
- **Pairing by code, per-device secret.** The device generates a 64-hex secret
  (NVS), `POST /api/displays/pair/` shows an 8-character code (10 min); a
  department admin claims it on `/desks/manage/displays` and picks a room.
  Only the SHA-256 of the secret is stored; the secret is scoped to its room;
  revoking invalidates it at once. The open pairing endpoint is throttled per
  client IP (12/min, `common.net.client_ip`) and caps pending requests;
  button events are rate-limited per display.
- **No new service, no new env var.** Devices use the existing backend over
  HTTPS; the firmware validates the certificate against bundled roots
  (ISRG X1 + X2). Firmware lives in `firmware/door-display/` (PlatformIO).

## Consequences
- One layout implementation; every change ships with the backend. Cost: each
  key press in an interaction is a network round trip (~0.3–1 s).
- Door signs show names in the corridor (desk holders unless opted out;
  meeting rooms always) — the privacy page and the staff-council summary
  mention it.
- Whoever stands at the door can check in/out a reservation or take a free
  meeting room, even without access-group rights; accepted by the product
  owner. Physical access to a device exposes its (unencrypted) NVS secret
  until flash encryption arrives with the later setup mode.
- Firmware needs a reflash only for client-side changes (Wi-Fi, server URL,
  root CAs).

## Alternatives considered
- **B — server sends JSON, device draws:** instant feedback and less data, but
  every layout change means reflashing all displays and the rules would exist
  twice (server and firmware). Rejected.
- **Hybrid (selection frame drawn locally):** only if A feels too slow in the
  test; not needed so far.
- **ESPHome for the firmware:** the selection/confirm/timeout flow is awkward
  there; Arduino/PlatformIO was chosen.
