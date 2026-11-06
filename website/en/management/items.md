---
title: Items, defects and QR labels
description: Maintain the inventory — products and their items, status and properties, defects with optional GitLab issues and printable QR labels.
---

# Items, defects and QR labels

A **product** is the catalog entry, such as "Sony Alpha 7 IV". An **item**
is a single unit of it, with its own inventory number (e.g. MED-001), its
own pool and its own status. People book the product; Ausleihbar assigns a
free item.

## The Items page

Lending desk → Inventory → **Items** lists the products. A click on the
arrow expands a product and shows its items.

!["Items" page with the filters All pools, All statuses, All product types and No property filter, the buttons "+ New product" and "+ New item" and the product list with labels such as "2 available", "1 overdue · due 04/11/2026", "1 lent out · until 06/11/2026" and "1 defective"; the Sony Alpha 7 IV is expanded and shows MED-0001 and MED-0002 as Available and MED-0003 as Defective with a note](../bilder/theke-gegenstaende.png)

On every product, labels show at a glance how many items are **available**,
**lent out** (with the return date), **overdue**, **blocked**,
**defective** or **retired**. In the product's **⋮** menu: **Edit
product**, **Add item**, **Delete**.

The expanded table shows, for each item, the inventory number, pool,
status, condition and — if it is out — "lent out until …" or "overdue, due
…". The columns can be sorted. In the item's **⋮** menu: **Edit**,
**Duplicate** (for more identical units) and **Delete**.

!!! info "All products, your items"
    Products belong to the shared catalog, so you see all of them — even
    those your pool has no units of ("0 items"). You only see and edit
    items in your own pools.

### Filtering

- **Pool**, **Status** and **Product type**,
- the search field for product, inventory or serial number,
- the **property filter** for date properties maintained on the item, such
  as "last maintenance": **older than** a date or **empty**. This way you
  find, for example, all items whose inspection is due. The chosen
  property then also appears as a sortable column.

### Status

| Status | Meaning |
| --- | --- |
| **Available** | can be booked and handed out |
| **Blocked** | temporarily taken out of lending |
| **Defective** | broken, not lent out ([Defects](#defects)) |
| **Retired** | permanently out of service |

You change the status directly in the table using the dropdown. If you
choose **Defective**, Ausleihbar asks for a short description of the
problem.

### An item in detail

A click on the inventory number opens the item's details page: product,
pool, QR code, storage location, value, procurement date, warranty end,
serial number, institution and the properties maintained on the item. In
addition:

- **Condition (lender-only):** a rating from 1 to 5 stars with optional
  details — invisible to borrowers.
- **Current defect** with **Mark defective** or **Resolve defect (mark
  available)**.
- **Defect history** and **Lending history**.

Use the pencil to edit the item.

### Adding an item

**+ New item** (or **Add item** on the product) opens the form. **Product**
and **Pool** are required; Ausleihbar suggests the **Inventory number**
based on the pool. Further fields: serial number, status, storage location,
value, procurement date, warranty end, procuring and owning institution and
the product type's properties that are maintained on the item.

Under **Lending duration**, a single item can get its own minimum and
maximum durations; otherwise it takes those of the product
([Lending duration](products.md#lending-duration)). Under **Advanced** you
find the **QR code ID** — it is assigned automatically. Only change it if
you want to reuse a label that has already been printed.

!!! tip "Deleting moves to the trash"
    Deleted products and items go to the
    [trash](settings.md#trash) and can be restored there until they are
    automatically removed for good.

## Defects

Lending desk → Inventory → **Defects** collects all items in your pools
that are marked as defective (**Currently defective**) or have been before
(**Previously defective**) — with date, note, how often the item has
already had a problem and, if applicable, the GitLab issue. A click on the
item opens its details page, where you repair or retire it.

!["Defects" page: the "Connect GitLab" button, below it "Currently defective (1)" with MED-0003 · Sony Alpha 7 IV in the Media Lab, defective since 13/10/2026 with the note "Viewfinder shows dead pixels, repair requested.", history "1× problem" and no ticket; "Previously defective (0)" is empty](../bilder/theke-defekte.png)

What happens to the bookings when an item is marked defective is described
in [Reporting defects](handout.md#reporting-defects). Depending on the
setup, Ausleihbar also regularly reminds the lending team by email of items
that have been defective for a while, so that they get repaired or retired.

### Connecting GitLab (optional)

If your team tracks repairs in GitLab, Ausleihbar can automatically create
an issue for every new defect. You set up **Connect GitLab** per pool:

1. **GitLab project URL:** the full address of the project including the
   server, e.g. `https://gitlab.example.org/team/devices`.
2. **Access token:** In GitLab, under Settings → Access Tokens, create a
   project access token with the role "Reporter" and only the "api" scope,
   and paste it here.
3. **Save.** After that the token is never shown again, only whether one
   is stored.

Every issue links back to Ausleihbar. If GitLab is ever unreachable, the
defect is saved anyway. To switch it off, clear the URL or click **Remove
token**.

## QR labels

Every item has its own QR code. Lending desk → Inventory → **QR labels**
prints them as stickers. At the desk you scan them for handout and return
([QR page](handout.md#the-qr-page)); borrowers who scan them with their
phone land on the product page.

!["QR labels" page: pool Media Lab, field "Created since", format "Tape · 36 mm (Brother P-touch PT-E920BT)", the button "Print 18 labels", the selection list with MED-0001 to MED-0009 and below it the label preview with QR code, inventory number, product and pool](../bilder/theke-qr-etiketten.png)

1. Choose the **Pool**. With **Created since** you limit the list to newly
   added items, for example after a delivery.
2. Choose the **Format** that matches your printer: tapes for Brother
   P-touch (24 or 36 mm), rolls for Brother QL and DYMO, or an A4 sheet to
   cut out.
3. Tick the items (**Select all** / **Select none**) and click **Print …
   labels**.

Each label shows QR code, inventory number, product and pool.
