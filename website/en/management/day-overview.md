---
title: Day overview
description: The lending desk's start page — what needs confirming, handing out, taking back and what is overdue today.
---

# Day overview

The **Day overview** is the lending desk's start page. It shows, for one
day, what is coming up at the desk, and it is the fastest way to all
bookings that need work right now.

![Kim's day overview on Friday, 6 November 2026: pool filter "All pools", Media Lab and Podcast Studio, the counters Pickups 0/2, Returns 0/2, Overdue 2 (needs attention), To confirm 2 and Currently lent out 3, below them the section "To confirm (2)" with two bookings, each with a message and a "Confirm" button](../bilder/theke-tagesuebersicht.png)

## Choosing day and pool

- Use the arrows to move one day forward or back; **Today** jumps back to
  today.
- A click on the date opens a month calendar. For every day it shows how
  many pickups and returns are due; closed days are gray.
- If you look after several pools, the buttons above filter by one pool.
  **All pools** shows everything you are responsible for. Your choice is
  remembered.

## The counters

| Counter | Meaning |
| --- | --- |
| **Pickups** | Bookings with a pickup on this day, as "completed / total" |
| **Returns** | Bookings whose last day is this day, as "completed / total" |
| **Overdue** | Bookings with a missed pickup or an overdue return; red with "needs attention" as soon as there are any |
| **To confirm** | New bookings waiting for your confirmation |
| **Currently lent out** | Items that are out right now — regardless of the chosen day |

Bookings are counted, not individual items (except for "Currently lent
out"). A click on a counter jumps to the matching section.

## The sections

Below the counters, the bookings appear in up to five sections. Each can be
expanded and collapsed; empty sections are left out.

**To confirm**
:   All bookings with the status **Awaiting confirmation**, no matter for
    which day — the oldest request first, in the order in which you should
    work through them.

**⚠ Overdue**
:   Bookings whose pickup was missed on an earlier day or whose return is
    past due. Here you can still **Hand out** or record the **Return** after
    the fact and **Remind** the person.

**Pickups**
:   Confirmed bookings whose period starts on this day, with the **Hand
    out** button.

**Returns due**
:   Handed-out bookings whose last day is this day, with the **Return**
    button.

**On-site use today**
:   Bookings of products for on-site use **without handout** whose period
    touches this day. They don't need you; you just see who is coming.
    On-site products **with** handout run through pickups and returns like
    any other loan.

    If someone finishes early and forgot to end the use themselves, click
    **End use** on an ongoing use. The rest of the period then becomes free
    for others. You can also do this under
    [All bookings](bookings.md).

Each booking shows the pool, the person (a click opens their
[profile](bookings.md#a-persons-profile)), the booking number, the status,
the items with inventory number and period and, if there is one, the
person's **message**. More actions are in the **⋮** menu.

## Confirming bookings

New bookings arrive with the status **Awaiting confirmation**. The items are
already reserved for the person; by confirming, you agree that the loan can
take place as booked.

1. Read the booking and its message.
2. If you want to tell the person something, for example suggest a pickup
   time, choose **⋮** → **Add a message** in the menu. The text
   ("Message to the borrower (optional)") is added to the confirmation
   email.
3. Click **Confirm**.

The person receives the [confirmation email](../guide/emails.md#confirmation-email)
with the pickup QR code and a calendar entry.

!!! info "Orders across several pools"
    If someone books from several pools in one cart, a separate booking is
    created per pool, and each lending team confirms its own. If your
    confirmation completes the confirmation of the whole order, a combined
    email goes out immediately. Otherwise Ausleihbar collects the partial
    confirmations and sends them at a fixed time (see
    [Notifications](settings.md#notifications)) — unless the pickup starts
    earlier or that time has already passed.

If a booking doesn't work, you can decline it via **⋮** → **Cancel
booking**. The person receives an email about the cancellation; in the
dialog you can add a **Message to the person**, such as the reason or a
suggested alternative.

## Overdue items

There are two cases of overdue items:

- **Pickup missed:** The person didn't come on the first day. If they still
  come, hand out as usual with **Hand out**. If they don't, you can cancel
  the booking and so free the items again. Once the whole period is over
  without a pickup, Ausleihbar cancels the booking automatically anyway
  (depending on the setup, as a scheduled job).
- **Return overdue:** The items are still out, the last day is over. Take
  them back with **Return** when they are returned.

With **⋮** → **Remind** you immediately send the person an email listing
everything that has not yet been picked up or returned. Ausleihbar also
sends reminders by itself about once a day (depending on the setup, as a
scheduled job). How often and when the person was last reminded is shown on
the booking ("🔔 Reminded 2× · last …").

!!! tip "Give a strike"
    For a clearly late return, a damaged item or repeatedly missed pickups,
    you can give a strike at your discretion via **⋮** → **Give a strike** —
    this never happens automatically. See [Strikes](bookings.md#issuing-strikes).

How handing out and taking back work in detail is described in
[Handout, return and QR codes](handout.md).
