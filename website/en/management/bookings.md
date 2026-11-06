---
title: All bookings and strikes
description: Find and edit every booking in your pools, issue strikes and view a borrower's profile.
---

# All bookings and strikes

The day overview shows what is due today. **All bookings** (Lending desk →
Bookings & handout) shows everything — past, ongoing and future bookings of
your pools, including cancelled ones.

!["All bookings" with the search field, the switch "Lending start | Booking received" and the period "All"; below them a booking by Alex Beispiel awaiting confirmation, a confirmed booking by Mika Probe with three items and the "Hand out" button, and the start of another confirmed booking in the Podcast Studio](../bilder/theke-buchungen.png)

## Searching and filtering

- **Search field:** booking number, the person's name or product ("Search
  by booking number, customer or product…").
- **Lending start | Booking received:** sorts by the start of the period or
  by when the booking was received.
- **Period:** All, Today, This week, This month or Custom with From/To.

## What you can do with a booking

The bookings look like those in the day overview and have the same actions,
depending on their status:

| Status | Actions |
| --- | --- |
| **Awaiting confirmation** | **Confirm**, optionally with a message ([as in the day overview](day-overview.md#confirming-bookings)) |
| **Confirmed** | **Hand out** |
| **Picked up** | **Return** for the handed-out items, **Hand out** for those still open |

In the booking's **⋮** menu:

- **Give a strike** — see [below](#issuing-strikes).
- **Cancel booking** — as long as nothing has been handed out. If items are
  out, take them back first. The items become free again immediately. The
  person receives an email about the cancellation; in the dialog you can
  add a **Message to the person**, such as the reason or a suggested
  alternative. The message only appears in the email and is not stored.

On a single item (small **⋮**): **Mark defective** or **Mark repaired**
([what happens then](handout.md#reporting-defects)).

You can swap an item of a booking for another or add an extra one during
handout on the [QR page](handout.md#handing-out-by-scan).

!!! info "Labels on the booking"
    **Outside the lending-duration limit** — created at the desk via walk-in
    lending with a period outside the limits.
    **🔔 Reminded …** — the person was reminded because of an overdue item.
    **On site** — the item is used on site; **No hand-out** additionally
    means: without the desk.

## Issuing strikes

A strike is a warning with a reason. Ausleihbar **never** issues one
**automatically** — you decide whether a situation justifies a strike.
Typical reasons are a **clearly late return** or an item returned
**damaged or dirty**; a single missed pickup usually isn't one, repeatedly
not showing up can be. Strikes count across all pools and expire after a
fixed time; from a certain number of active strikes, Ausleihbar blocks the
account automatically (set in the [strike rules](people.md#strike-rules)).
What borrowers see of this is described in
[Strikes and blocks](../guide/strikes.md).

1. On the booking, open **⋮** → **Give a strike**.
2. Enter the **Reason**. It appears in the email and for the person under
   "Your strikes".
3. Optional: a **Personal message to the person**. It only appears in the
   email.
4. Check the **Email preview** and the note below it on what the strike
   will cause — e.g. "This will be active strike no. 2 — no block yet." or
   "… — the account will be blocked until …."
5. Click **Give a strike**.

![Dialog "Give a strike — Jona Muster" with the reason "Reservation neither picked up nor cancelled", the empty field for a personal message, the email preview "Strike for your booking R-00223" with expiry date, number of active strikes, block threshold and the pool's contact details, and below it "This will be active strike no. 2 — no block yet."](../bilder/theke-strike.png)

!!! note "Deleting and unblocking is done by the administration"
    Lenders issue strikes; only admins can delete them. Likewise, only the
    administration can lift a block
    ([Users](people.md#users)). If the person has no email address, no
    email is sent; the strike counts anyway.

## A person's profile

A click on the name on a booking opens the person's profile. There you see:

- whether the account is blocked ("Blocked until …", "Blocked indefinitely"
  or "Not blocked") and how many strikes are active,
- all **Strikes** with reason, personal message, who issued them and until
  when they count,
- the **Booking history**, split into Upcoming, Handed out and Completed.

Here, too, you can **Give a strike** — as a lender for people who have
booked in one of your pools.
