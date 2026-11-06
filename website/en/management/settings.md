---
title: Settings
description: For admins — block days and public holidays, the cart hold time, custom mail texts and send times, content pages, catalog import and export, and the trash.
---

# Settings

Administration → **Settings** brings together everything that applies to
the whole installation.

## Block days and public holidays

On a **block day** no pickup and no return is possible; hourly and
single-day bookings can't take place on it. Multi-day periods may span a
block day. Borrowers see it in the calendar with a lock.

!["Block days" page: at the top "Public holidays" with country DE, state NI and the button "Save & load holidays", below it the form with From, To (optional), scope "All pools (system-wide)" and reason, and the list: staff outing and stocktaking in the Media Lab, Christmas Day and Second Day of Christmas in all pools](../bilder/admin-sperrtage.png)

**Public holidays**
:   Enter **Country** and **State / subdivision** (e.g. DE and NI) and
    click **Save & load holidays**. Ausleihbar enters the public holidays
    as system-wide block days for the whole booking horizon — as far ahead
    as the pool with the longest horizon allows bookings. Save again to
    refresh. You can remove individual holidays from the list if you are
    open anyway.

**Custom block days**
:   **From**, optionally **To**, the **Scope** — **All pools
    (system-wide)** or a single pool — and optionally a **Reason**, e.g.
    "Company holidays". Then **Add block**. The list hides past block days;
    you can show them again.

!!! warning "What happens to existing bookings"
    If a new block day falls on existing bookings, Ausleihbar adjusts them:
    a pickup on the block day moves to the next open day, and so does a
    return on the block day. If the moved period no longer fits the item,
    Ausleihbar takes a free identical item; otherwise the booking is
    cancelled. Single-day and hourly bookings on the block day are
    cancelled. The people affected receive an email, and you see how many
    bookings were moved and cancelled.

You can also maintain block days for a single pool directly in the
[pool form](catalog.md#pools).

## Cart

When someone adds a product to the cart, an item is reserved for them. The
**Cart hold (minutes)** determines for how long (30 minutes unless you set
your own value). Every action in the cart renews the hold; once it expires,
the item is free again. This does not affect submitted bookings. What this
looks like for borrowers is described in
[Held – but not forever](../guide/cart.md#held--but-not-forever).

## Notifications

Here you customize the emails to borrowers. The personal salutation, the
booking number, the booking details and the link always stay in; your text
is inserted around them.

!["Notifications" page: on the left the send time for held confirmations (17:00) and the fields for intro and closing text for submitted reservations, each EN/DE; on the right the choice of emails (Reservation received, Confirmation, Rescheduled, Cancelled, Reminder, defect notice, Item missing, Pickup reminder), the preview language and the live preview with sample data](../bilder/admin-benachrichtigungen.png)

**Send time for held confirmations**
:   For orders across several pools, Ausleihbar collects partial
    confirmations and sends them at this time
    ([more on this](day-overview.md#confirming-bookings)).

**Custom texts**
:   Each email has matching fields, such as intro and closing text for
    submitted reservations, a reason and an extra paragraph for a
    rescheduling or cancellation because of a block day, a paragraph in the
    overdue reminder (e.g. "Late returns may lead to a strike.") and in the
    email sent when a reserved item becomes unavailable. All fields are
    optional and have German and English. If one language is empty,
    Ausleihbar uses the other; if both are empty, the built-in default
    text.

**Reminder before pickup**
:   **Send a pickup reminder one day before** switches the email on the day
    before the pickup on or off. It contains address, opening hours and
    directions. The **Send time** sets from when on the day before it goes
    out; plus an optional custom text, such as "Please bring your student
    ID."

**Preview**
:   On the right you see every email with sample data, in German or
    English. Colors show what comes from you (**Your text**), what from the
    pool (**From the pool**) and what is inserted automatically.

Notes that only concern one pool are maintained on the pool (**Note in
borrower emails**, see [Pools](catalog.md#pools)). Which emails borrowers
receive is described in [Emails and reminders](../guide/emails.md).

## Pages

Under **Pages** you maintain content pages such as the legal notice or the
privacy policy. Each page has a **Title**, a **URL slug**, a formatted
**Body** (German and English) and is **Published** or a **Draft**. With
**Show in footer** it appears as a link in the footer; you set the order
with **Reorder**.

Two built-in pages have their own forms:

- **Welcome page** — the welcome text for visitors who are not signed in.
  Below it, Ausleihbar automatically lists the pools with their images.
  The **Lending logo** is shown in the lending area's header, for
  everyone.
- **Lending start page** — what signed-in people see on the start page:
  whether the rows **"Popular right now"** and **"New arrivals"** appear
  and for how many days new products carry the "New" label.

!!! note "Maintaining the privacy policy"
    The privacy page is written by hand; Ausleihbar does not generate it.
    It needs to be reviewed whenever what data is stored changes, for
    example with a new data retention rule
    ([Data retention](people.md#data-retention)).

## Import and export

**Import / export** exports the catalog as a ZIP archive or transfers it to
another installation: sections, categories, product types, products, sets,
pools and inventory, with images, plus the pages (CMS) and the settings for
the shop and start page. **Bookings, users and other personal data are
never included.**

- **Export:** **Export whole system**, or a single pool with the products
  its items need (**Export pool**).
- **Import:** Choose an archive of up to 2 GB and first run **Dry run
  (preview)** — it shows what would be created, updated or converted,
  without saving anything. Ausleihbar recognizes existing entries by their
  key (name, inventory number …) and updates them; missing ones are
  created.

!!! warning "No substitute for a backup"
    The archive only contains catalog, pages and settings. A complete
    backup requires backing up the database and media files (see
    [Installation](../installation.md)).

Inventory from **leihs** is taken over by a command-line command of the
installation; details are in the
[leihs guide in the repository](https://github.com/virtUOS/ausleihbar/blob/main/docs/leihs-import.md).
The archive format is described in
[data-transfer.md](https://github.com/virtUOS/ausleihbar/blob/main/docs/data-transfer.md).

## Trash

Deleted sections, categories, product types, products, items, sets and
pools first go to the **Trash**. There you see who deleted them when and
when they will be deleted permanently and automatically.

- **Restore** brings an entry back.
- **Delete permanently** or **Empty trash** removes entries immediately —
  this cannot be undone.
- Under **Retention** you set how many days deleted entries are kept (30
  unless you set your own value).
