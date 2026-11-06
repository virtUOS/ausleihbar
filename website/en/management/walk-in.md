---
title: Walk-in lending
description: Lend spontaneously to someone at the lending desk — hand out right away or create a confirmed booking for later.
---

# Walk-in lending

If someone is at the desk without a booking, you create the loan yourself
with **Walk-in lending** (Lending desk → Bookings & handout → Walk-in). The
pool's lead time and booking horizon don't apply here; Ausleihbar still
checks whether the items are free in the period.

## Two modes

**Hand out now**
:   The items are handed out to the person right away; you only choose the
    return date (for hourly products also the return time).

**Booking for later**
:   Creates a **confirmed** booking for the person, who picks it up at the
    desk later — for example when someone asks by phone or email. You
    choose start and end (**From** / **Until**, for hourly products also
    **Start time** / **End time**).

In both cases the person receives the
[confirmation email](../guide/emails.md#confirmation-email) just as for a
loan they booked themselves.

## Step by step

![Walk-in lending in the "Hand out now" mode: 1. Borrower Alex Beispiel, 2. Items with the pool Media Lab, the products grouped by section and category and the selected Canon EOS R6 Mark II (✓ MED-0004), 3. Period with return date 09/11/2026, 4. Confirm with an optional note and the "Hand out" button](../bilder/theke-direktausleihe.png)

1. **Borrower:** Search for the person by name, username or email (at
   least three characters). The person must have signed in to Ausleihbar
   at least once. No walk-in loan can be created for **blocked** accounts —
   Ausleihbar reports this when you create it.
2. **Items:** Choose the pool and then the products. The list is grouped
   by section › category and shows the lending type and maximum duration;
   you can search it at the top. Use **−** / **+** to set the quantity.
   Ausleihbar picks free items and shows their inventory numbers (e.g.
   "✓ MED-0004"). If you want to hand out a specific one, choose **Choose
   another item**.
3. **Period:** Enter the return date or From/Until. Only then does
   Ausleihbar check availability ("Not available in this period", "Only 1
   of 2 available"). Times only apply to hourly products; daily ones always
   cover whole days.
4. **Confirm:** Optionally enter a **Note**, such as the reason for the
   loan. Then click **Hand out** ("Hand out now" mode) or **Create
   booking** ("Booking for later" mode).

Afterwards the booking appears like any other in the day overview and in
[All bookings](bookings.md).

!!! note "Note as a required field"
    If the pool requires a message with orders (setting in the
    [pool](catalog.md#pools)), the note is required here too: "A note is
    required for this pool."

!!! info "Switching pools"
    Walk-in lending always runs through **one** pool. If you change it or
    the mode, the items chosen so far are removed.

## Warnings instead of bans

At the desk, you decide. Some things that would prevent a booking in the
lending area are only a notice here:

- **Lending duration:** If the period is outside the minimum or maximum
  duration, "Outside the lending-duration limit (…)." appears. You can lend
  anyway. The booking then carries the label **Outside the lending-duration
  limit** in the lists. When Ausleihbar picks the item itself, it prefers
  one whose limits fit.
- **Closed days and opening hours:** In the **Hand out now** mode,
  Ausleihbar only warns if the return falls on a closed day or outside the
  opening hours ("Return on a closed day", "Outside opening hours"). For
  **Booking for later**, on the other hand, pickup and return must be on
  open days and within the opening hours.

What never works: lending items that are already booked, defective or
blocked in the period, and lending to blocked accounts.

!!! tip "Buffer times"
    A buffer time between two loans that is set on the product does not
    apply to walk-in lending.

On-site items without handout are only booked here too, not handed out.
