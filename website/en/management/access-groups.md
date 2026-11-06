---
title: Access groups
description: Maintain at the lending desk who may see and book your pools' items — the members of your pools' access groups.
---

# Access groups

If one of your pools is restricted to certain people, an **access group**
controls this: only its members see and book the pool's items (plus the
lending team and all admins). You maintain the members of these groups
yourself — under Lending desk → **Bookings & handout** → **Access groups**.
So you don't have to ask the administration for every new person.

## Which groups you see here

Only **pure access groups** that unlock at least one of your pools appear
here. Groups that grant **rights** — lender for a pool, administrator — as
well as the [system groups](people.md#system-groups) are deliberately
missing: only the administration grants rights. Creating new groups,
renaming them or changing their pools is also up to the administration
alone ([People and access](people.md#access-groups)).

Each group has its own card:

- The group's **name** and description.
- The group's **pools** in their pool color. If the group also unlocks a
  pool you don't look after, it says **(not your pool)** there.
- If the group has a **claim rule**, a line such as "Also a member
  automatically: everyone with `eduPersonAffiliation ∈ {faculty}`".
- The **Members** with name and email.

!!! warning "One group, several pools"
    If a group also unlocks other lending teams' pools, every change applies
    there as well. Whoever you add may then also see and book those pools.

## Adding and removing members

1. In the **Add person** field, type at least three characters of the
   name, username or email.
2. Choose the person from the list. They are a member immediately and may
   see and book the group's pools.

The **✕** next to a member removes them again after a confirmation; the
person can then no longer see the group's pools, unless they still have
access through another group, a login rule or as a lender.

Only people who have signed in at least once can be found. You can't add a
deactivated account.

!!! note "Members marked ‘automatic’"
    Anyone who is a member through the claim rule carries the label
    **automatic** and has no ✕: the membership is determined anew from the
    single sign-on details at every sign-in. If such a person should not
    have access, the administration has to change the rule.

## No group for your pools?

Then it says "There is no access group for your pools." Either your pools
are open to everyone signed in, or they are restricted through a group with
rights that only the administration maintains. If access should be
restricted (differently), the administration creates an access group.
Admins find a link to the access group management on the page.

!!! info "Privacy"
    On this page you see the name and email of all members of your pools'
    access groups — including those who only belong through the claim rule.
    Use this information for lending only.
