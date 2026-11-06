---
title: Creating products
description: Create and edit a product in the catalog — product type, texts, images, lending type, on-site use, lending duration, categories, complementary items and return information.
---

# Creating products

Products are the catalog that borrowers see in the lending area. A product
does not belong to a pool; which pools lend it follows from its
[items](items.md). All lenders can create and edit products.

You open the form under Lending desk → Inventory → Items with **+ New
product**, or on the product via **⋮** → **Edit product**. You save with
**Save** in the bar at the bottom edge.

![Product form "Edit Sony Alpha 7 IV", section "General": product type Camera, title and short description each with the language switches EN and DE, product details with text formatting and below it the field for images; at the bottom the bar with Save and Cancel](../bilder/produktformular.png)

## General

- **Product type:** required. The type determines which
  [properties](#properties) the product has. Product types are maintained
  by the administration ([Product types](catalog.md#product-types)).
- **Title** (required) and **Short description** — a short sentence on what
  the product is.
- **Product details:** formatted text with headings, lists, links and
  images, e.g. what is included.
- **Images:** drop images here or click; several are possible. You change
  the order by dragging; the first one is the **Cover**.

!!! info "German and English"
    Texts have the switches **DE** and **EN**. A dot shows whether the
    language is filled in. If a language is missing, borrowers see the
    other one. If **machine translation** is set up in your installation,
    you can take over a text from the other language with "Translate from
    …".

!!! tip "Fill from PDF (AI) — only if set up"
    If an AI service is connected in your installation, **Fill from PDF
    (AI)** becomes available once you have chosen the product type. You
    upload a manual or data sheet (max. 20 MB), and Ausleihbar fills in the
    title, descriptions and properties — only empty fields; existing
    entries stay. For this, the PDF's text is sent to the AI service; the
    PDF itself is not stored. Check the result before saving. The AI
    support is always optional.

## Lending terms

**Type of use**
:   **Loan** — the item is taken away.
    **On-site use** — the item or room is used on site during the booked
    period, such as a studio or a 3D printer. Then there is also **Hand-out
    at the desk required**: when ticked, the booking runs through handout
    and return like a loan; when unticked, it is only a time slot and is
    closed automatically after it ends. What this looks like for borrowers
    is described in [On-site use](../guide/pickup-and-return.md#on-site-use).

**Lending type**
:   **Days** or **Hours** — whether whole days or individual hours are
    booked in the calendar.

### Lending duration

**Min duration** and **Max duration** limit how short or long a booking may
be, in the unit of the lending type. Without a value of its own (**Inherit
from pool**), the pool's default applies. The limit is looked up from the
bottom up:

1. a value of its own on the **item**,
2. otherwise the value on the **product**,
3. otherwise the **pool's** default lending duration,
4. otherwise no limit.

In the lending area, a period outside the limits can't be added to the
cart; at the desk it is only a
[warning](walk-in.md#warnings-instead-of-bans). If a minimum duration
doesn't fit a pool's maximum duration, the form warns that the items there
would not be bookable.

**Buffer between two loans**
:   Minimum time between two loans of the same item, for example for
    checking, charging or cleaning. Does not apply to walk-in lending.

**Notify borrower if missing — lead**
:   If an item is still not back (overdue) this long before a pickup,
    Ausleihbar moves the upcoming booking to a free item — or writes to the
    person if none is free. 0 = off.

## Placement in the shop

- **Categories:** where the product appears in the shop navigation. A
  product can be in several categories. The category tree is maintained by
  the administration ([Categories](catalog.md#categories)).
  If AI is set up, **Suggest categories** proposes up to three matching
  existing categories; only what you select is taken over.
- **Complementary devices:** products that go well with it, such as a
  tripod for the camera. They appear on the product page with their pools.
  The link works in both directions: the other product shows this one as
  well. The order can be changed.

## Properties

Here you fill in the product type's properties, such as sensor or
resolution for a camera. Required fields are marked. Whether a property is
visible in the shop is set by the administration in the product type.
Properties maintained on the individual item (e.g. "last maintenance") are
not here but in the [item's form](items.md#adding-an-item).

## For lenders

**Return information**
:   A note shown only to the lending team at the return, e.g. "Battery,
    charger and memory card complete? Check the viewfinder for scratches."
    If it is filled in, every return of the product opens the
    [Check the return](handout.md#taking-back) dialog. Invisible to
    borrowers.

!!! tip "After saving"
    A new product only becomes bookable once it has at least one available
    item in an active pool. So add the units right away via **⋮** → **Add
    item**.
