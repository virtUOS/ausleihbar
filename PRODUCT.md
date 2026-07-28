# Product

## Register

product

## Users

Students and staff of Universität Osnabrück borrowing equipment (cameras,
audio gear, laptops, rooms) — often on a phone, between lectures, in a hurry.
Secondary users: lenders running the lending desk (tablet/desktop at the
counter) and admins configuring the catalog (desktop). The borrower is a
casual, infrequent user who must succeed on first contact without training;
desk and admin users are daily power users who value density and speed.

## Product Purpose

Ausleihbar is the university's device-lending shop: browse the catalog, check
availability, reserve, pick up via QR, return. Success = a first-time student
completes a reservation on their phone in under two minutes, and the lending
desk processes pickups/returns without friction. It replaces an aging system
(leihs) and email/paper workflows.

## Brand Personality

Modern, friendly-playful in the details, highly functional. The tone of a
well-run university makerspace: welcoming and optimistic, never bureaucratic,
never salesy. Warmth comes from small moments (micro-interactions, friendly
empty states, human copy) — the interface itself stays calm and disappears
into the task. Independent identity: a neutral surface with one warm accent;
the university logo sits alongside without the UI imitating university CI.

## Anti-references

- **Behörden-/Verwaltungssoftware**: sterile gray form deserts, dense
  bureaucratic language, no visual hierarchy.
- **Amazon / commercial e-commerce**: price-war aesthetics, dense promotional
  grids, dark patterns, urgency banners.
- Also avoid the generic AI-SaaS template look (gradient heroes,
  glassmorphism, identical card grids).

## Design Principles

1. **Phone-first borrowing.** Every borrower flow is designed at 390px first;
   desktop is the enhancement. Touch targets ≥44px, thumb-reachable actions.
2. **Calm surface, warm moments.** Restrained neutral UI; the personality
   lives in deliberate details — one accent color, friendly empty states,
   small state-driven motion. Delight is saved for moments, not pages.
3. **Earned familiarity.** Standard affordances done excellently (buttons,
   forms, navigation). No invented controls; the tool disappears into the
   task of borrowing.
4. **Accessible by default.** New components ship with contrast, keyboard
   path, focus style, labels and reduced-motion behavior — not as a later
   audit pass.
5. **One vocabulary everywhere.** Shop, lending desk and admin share the same
   tokens and component shapes; the desk/admin may be denser, never different.

## Accessibility & Inclusion

Target: WCAG 2.1 AA / BITV 2.0-orientiert (public-institution context).
Concretely: text contrast ≥4.5:1 (≥3:1 large), full keyboard operability with
visible focus, semantic landmarks/headings, labels on all controls (the UI is
bilingual DE/EN — `lang` must follow the active language), touch targets
≥44px, `prefers-reduced-motion` alternatives for every animation, and status
conveyed by more than color alone (icons/text beside color badges).
