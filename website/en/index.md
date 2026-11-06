---
title: Borrow your university's items online
description: Ausleihbar is a lending system for universities — find cameras, microphones, laptops or rooms online, book them in the calendar and pick them up at the lending desk. Open source by virtUOS, Osnabrück University.
hide:
  - navigation
  - toc
---

<div class="al-hero" markdown>

<div class="al-hero__text" markdown>

<p class="al-eyebrow">Open Source · virtUOS, Osnabrück University</p>

<h1 class="al-hero__title">Your university's items, <span>borrowed online with ease.</span></h1>

<p class="al-hero__lead">
Ausleihbar works like an online shop for everything your university lends
out: look up a camera, microphone, laptop or podcast studio, see the free days
in the calendar, add it to your cart and submit. The lending team confirms
the booking, hands the items out at the lending desk and takes them back
again.
</p>

<div class="al-hero__actions" markdown>
[Guide for borrowers](guide/index.md){ .md-button .md-button--primary }
[For lenders & admins](management/index.md){ .md-button }
[:fontawesome-brands-github: Source code on GitHub](https://github.com/virtUOS/ausleihbar){ .md-button }
</div>

</div>

<figure class="al-shot al-shot--hero" markdown>
![Ausleihbar home page: the greeting “Moin, Alex!”, the “My bookings” card with a notice about an overdue item, tiles for the sections Media equipment and Rooms & workspaces, and the “Popular right now” row](bilder/start.png)
</figure>

</div>

<ul class="al-facts">
  <li><strong>Single sign-on</strong><span>Sign in via OIDC with your university account</span></li>
  <li><strong>Open source</strong><span>Apache License 2.0, on GitHub</span></li>
  <li><strong>German &amp; English</strong><span>Interface, content and emails</span></li>
  <li><strong>Import from leihs</strong><span>Bring over your inventory from a leihs CSV export</span></li>
  <li><strong>Accessible</strong><span>Guided by WCAG 2.1 AA and BITV 2.0</span></li>
</ul>

## What Ausleihbar does { .al-section-title }

<p class="al-section-lead">One tool for both sides of the desk: borrowers find and book on their own, while lending teams keep track of handouts, returns and inventory.</p>

<div class="al-features" markdown>

<div class="al-feature" markdown>
![The “Photo & video” category with a breadcrumb trail, the subcategories Cameras and Tripods, filter chips and the products, split into daily and hourly lending](bilder/kategorie.png)

### Catalog and search

Sections, categories and subcategories lead you to the right item. Search
finds products, categories and sections; favorites remember what you need
often.

[:octicons-arrow-right-24: Finding items](guide/finding-items.md)
</div>

<div class="al-feature" markdown>
![Availability calendar for November 2026: the number of free units per day, a selected period from the 9th to the 11th and closed days marked with a lock icon](bilder/produkt-kalender.png)

### Availability in the calendar

Daily products show the free units per day; hourly products show each day's
utilization and the free hours. Closed days and lending durations are already
taken into account.

[:octicons-arrow-right-24: Product page and availability](guide/product-page.md)
</div>

<div class="al-feature" markdown>
![Cart with two pools, Media Lab and Podcast Studio, one item each, the hold time “held until”, the message field to the staff and the “Submit booking” button](bilder/warenkorb.png)

### One cart across several pools

Items from different lending locations go into one cart and are reserved
for you there. When you submit, one booking is created per pool, and each
lending team confirms its own.

[:octicons-arrow-right-24: Cart and submitting a booking](guide/cart.md)
</div>

<div class="al-feature" markdown>
![The “Interview kit” set page with a description, the notice “Available in Media Lab” and the three included products: camera, wireless microphone and tripod](bilder/set.png)

### Sets

Things that are often needed together are ready as a set — say, a camera,
wireless microphone and tripod for an interview. One click books everything
together, or nothing at all if something is missing.

[:octicons-arrow-right-24: Sets](guide/sets.md)
</div>

<div class="al-feature" markdown>
![“My bookings” with the “Overdue” section at the top and an upcoming, not yet confirmed booking below, each with pool, address and opening hours](bilder/meine-buchungen.png)

### Loan or on-site use

Besides lending, there is on-site use, for example for a podcast studio or a
3D printer — with or without a handout at the desk. “My bookings” always
shows what's coming up, what you have and what's overdue.

[:octicons-arrow-right-24: Pickup, return and on-site use](guide/pickup-and-return.md)
</div>

<div class="al-feature" markdown>
![Lending desk day overview with a pool filter, the date and counters for pickups, returns, overdue, to confirm and currently lent out, followed by two bookings to confirm](bilder/theke-tagesuebersicht.png)

### Lending desk

The day overview brings together pickups, returns, overdue items and new
bookings. Handout works by QR code: scan the pickup code from the email,
scan the items, done. Spontaneous loans happen right at the desk.

[:octicons-arrow-right-24: Day overview](management/day-overview.md) ·
[QR handout](management/handout.md) · [Walk-in lending](management/walk-in.md)
</div>

<div class="al-feature" markdown>
![Access group management: Administratoren, the Teaching staff group with the Makerspace pool and a claim rule, and the lender system groups with their members](bilder/admin-zugriffsgruppen.png)

### Access groups and roles

Pools can be restricted to groups, even automatically based on details from
the sign-in. Who lends and who administers is also handled by groups: one
lending team per pool, plus the administrators.

[:octicons-arrow-right-24: People and access](management/people.md)
</div>

<div class="al-feature" markdown>
![Lending desk statistics for 90 days: tiles for loans, users, late returns and loan duration, followed by the pool comparison](bilder/theke-statistik.png)

### Statistics

Loans, late returns, average loan duration and a comparison of pools over
any period you choose — with counts, never with names.

[:octicons-arrow-right-24: Statistics](management/statistics.md)
</div>

</div>

<div class="grid cards al-more" markdown>

-   :material-cellphone: __Made for smartphones__

    Catalog, calendar and cart work just as well on your phone as on your
    computer — no app needed.

-   :material-email-outline: __Emails with calendar entry__

    A receipt email, a confirmation email with a pickup QR code and an `.ics`
    file, and a reminder the day before pickup. [More about the emails](guide/emails.md)

-   :material-calendar-lock-outline: __Block days and holidays__

    Public holidays and closing days are never pickup or return days. If a
    new block day is added, affected bookings are rebooked or canceled — with
    an email to the borrowers.

-   :material-alert-octagon-outline: __Strikes__

    If an item comes back significantly late or damaged, the lending team can
    issue a strike at its own discretion — never automatically. Once a set
    threshold is reached, the account is blocked from new bookings.
    [More about strikes](guide/strikes.md)

</div>

## Who it's for { .al-section-title }

<div class="grid cards al-audience" markdown>

-   :material-account-outline: __Borrowers__

    ---

    Students and staff who need something for a seminar, project or thesis:
    sign in, search, book, pick up.

    [:octicons-arrow-right-24: To the guide](guide/index.md)

-   :material-handshake-outline: __Lending teams__

    ---

    Media lab, library, makerspace: confirm bookings, hand out and take back
    items, maintain the inventory, track defects, print QR labels.

    [:octicons-arrow-right-24: For lenders & admins](management/index.md)

-   :material-server-network: __Universities and IT centers__

    ---

    Run it yourself with Docker Compose, sign in through your own identity
    provider (OIDC), import your existing inventory from leihs.

    [:octicons-arrow-right-24: To the installation](installation.md)

</div>

<div class="al-cta" markdown>

<div markdown>

## Open source · run it yourself { .al-cta__title }

Ausleihbar is licensed under the Apache License 2.0 and runs as a Docker
Compose stack of PostgreSQL, Django and the React interface, served in
production behind Caddy with automatic HTTPS. The installation guide takes
you step by step to your own server. You'll find the source code on GitHub —
to review, run and contribute.

</div>

<div class="al-cta__actions" markdown>
[To the installation guide](installation.md){ .md-button .md-button--primary }
[:fontawesome-brands-github: virtUOS/ausleihbar](https://github.com/virtUOS/ausleihbar){ .md-button }
</div>

</div>
