---
title: People and access
description: For admins — users and their roles, access groups with claim rules and system groups, the strike rules and automatic data retention.
---

# People and access

Administration → **People & access** controls who may see, book, lend and
manage what. Accounts are created at the first sign-in through single
sign-on; you don't have to create anyone.

## Users

The list shows all accounts with username, name, email and their **Roles**
as labels: **Borrower**, **Lender · n** (for n pools), **Admin**, plus
**… strike** and **Blocked**. A click on a label filters the list by it, as
does **Inactive**; the search field finds name or email.

![User list: alex · Alex Beispiel (Borrower), docsadmin · Docs Admin (Admin), jona · Jona Muster (Borrower, 1 strike), kim · Kim Verleih (Lender · 2), lea · Lea Lernfeld and mika · Mika Probe (Borrower), robin · Robin Gesperrt (Borrower, Blocked) and sam · Sam Admin (Admin), each with email and a pencil for editing](../bilder/admin-nutzer.png)

The pencil opens an account's details:

- **Admin (full access to all pools and management)** — only admins with
  full system rights may set this checkbox. Otherwise you grant admin
  rights through the **Administratoren** group. If the admin role comes
  from a group of the identity provider, it can't be changed here.
- **Account active** — unticking it blocks sign-in.
- **Member of access groups** — the manual memberships.
- **Lender for … pools** — the pools the person looks after. If the right
  comes through another group, "via group …" is shown next to it.
- **Strikes & suspension** — all strikes with reason and expiry. Here you
  can **delete** a strike, **issue** one yourself and lift a block with
  **Unblock**.
- The person's **Booking history**.

!!! note "No locking yourself out"
    You can't change your own admin status, and you can't deactivate
    yourself — not even in a roundabout way through a group.

## Access groups

Access groups bundle people and give them rights. A group can grant three
things:

1. **Access to pools:** A pool without an access group is open to everyone
   signed in. As soon as a pool is listed in at least one group, only
   members of these groups can see and book it — plus its lenders and all
   admins.
2. **Lender for pools** (under **Advanced settings**): all members work at
   the lending desk of these pools.
3. **Administrator** (also under Advanced settings): all members are
   admins.

![List of access groups: Administratoren (System, right Administrator, member Sam Admin), Teaching staff (pool Makerspace, claim rule eduPersonAffiliation ∈ {faculty, employee}, member Alex Beispiel) and the system groups Verleiher Makerspace and Verleiher Medienlabor (with Kim Verleih)](../bilder/admin-zugriffsgruppen.png)

### Members: manual or by claim rule

You add members one by one (**Add member**) — or automatically through a
**claim rule**. A login claim is a piece of information that single
sign-on sends along at sign-in, such as department, study program or status
group.

- **Claim key:** e.g. `eduPersonAffiliation`, `groups` or `department`.
- **Matching values (comma-separated):** e.g. `faculty, employee`.

Anyone who has one of these values in the claim at sign-in is
automatically a member, in addition to the manually entered ones. In the
example above, this lets all teaching staff and employees book the
Makerspace. Under **Show all members, incl. via rule or system right** you
see all members with their origin: **manual**, **by rule** or **system
right**.

Lenders also maintain the members of pure access groups: at the lending
desk, under [Access groups](access-groups.md), they see the groups of their
pools and can add and remove manual members there. Groups that grant rights
(lender, administrator) and the system groups remain reserved for the
administration.

!!! warning "Never grant admin rights by rule"
    A group with a claim rule can't grant administrator rights. Only
    people entered manually get admin rights.

### System groups

Ausleihbar creates two kinds of groups itself. They carry the label
**System** and can't be deleted; Ausleihbar manages name, rule and rights,
and you can only edit members, description and pools:

- **Administratoren** — whoever is a member here is an admin.
- **Verleiher ‹Pool›** — one group per pool, created and renamed together
  with the pool. Its members are the lending team; you also maintain them
  in the [pool form](catalog.md#pools) under "Lenders".

## Strike rules

Here you set how long a strike counts and from when on strikes block an
account. Strikes are issued at the lending desk
([Issuing strikes](bookings.md#issuing-strikes)).

- **A strike counts for (days):** after that it no longer counts towards a
  block.
- **Escalation:** steps of the form "From *n* strikes: block for *x* days"
  or "permanent", e.g. from 3 active strikes 30 days, from 5 permanently.
  **+ Add step** adds more. Without steps, strikes never block
  automatically.
- **Save rules.**

When someone reaches a step, Ausleihbar automatically blocks the account
for new bookings. What blocked people see is described in
[Strikes and blocks](../guide/strikes.md).

## Data retention

Ausleihbar can automatically **anonymize** accounts that haven't been used
for a long time and no longer have any open loans (GDPR).

- **Enable automatic anonymization** — on or off (unless it is switched
  on, nothing is anonymized).
- **Anonymize after this many years of inactivity** — the period. Below it
  you see how many accounts would be anonymized now with this setting.

All personal data is removed in the process; the booking and item history
is kept under the placeholder "Gelöschter Nutzer". Admin accounts are
never affected. Anonymization runs as a scheduled job of the installation
and **cannot be undone**.

!!! tip "Privacy policy"
    If retention changes, the privacy page needs to be reviewed too
    ([Pages](settings.md#pages)).
