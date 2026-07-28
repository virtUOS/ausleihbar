# DESIGN.md — Ausleihbar

Visual contract for the shop (borrower) surface. The lending desk and admin
inherit the tokens (neutrals, font, focus styles) but keep their denser
utilitarian layouts until their own polish pass.

## Theme

"Uni-Makerspace bei Tageslicht": pure white ground, warm-tinted neutrals, one
honey-gold accent. Calm surface; personality lives in deliberate moments
(greeting marker, micro-motion, friendly empty states). Register: product.

## Color

Defined in `frontend/tailwind.config.js` (OKLCH, hue ≈ 91). Each custom color
carries the `/ <alpha-value>` placeholder so opacity modifiers
(`bg-slate-900/90`, `dark:bg-slate-800/50`) resolve — bare `oklch(...)` strings
make those utilities render transparent. Keep the placeholder on any new token.

- **Background**: pure white. Cards/wells: `slate-50`/`slate-100` (warm-tinted).
- **Ink**: `slate-900` body text; `slate-500` secondary; `slate-400` meta
  (≥4.5:1 on white — tuned darker than Tailwind's default).
- **Brand (honey)**: the single accent.
  - `brand-400` — primary CTA fill (with `slate-900` text, ≈8.6:1) and the cart
    badge; hover `brand-500`.
  - `brand-100/200` — selection fills (e.g. calendar days).
  - `brand-50` — illustrative emoji wells (pools, sets, empty states).
  - `brand-600` — focus rings, selected-state icons.
  - `brand-700/800` — accent text on white (≥4.5:1), wordmark "BAR".
- **Semantics unchanged**: green = available/success, red = unavailable/danger,
  amber = pending/warning, status pill palette as before.

## Dark mode

Auto/Light/Dark setting (Auto = system default), in the account menu. Toggled
by a `.dark` class on `<html>` (`darkMode: "class"`); a pre-paint script in
`index.html` mirrors `src/theme.tsx` to avoid a flash. Conventions for the
`dark:` sweep — depth comes from three neutral surfaces over a near-black canvas:

- **Canvas** (`bg-white` page root) → `dark:bg-slate-950`.
- **Surface** (cards, header, primary panels: `bg-white`) → `dark:bg-slate-900`.
- **Raised** (popovers, menus, wells, inputs: `bg-white`/`bg-slate-50`) →
  `dark:bg-slate-800`.
- **Borders**: `border-slate-200/100` → `dark:border-slate-800` on surface,
  `dark:border-slate-700` on raised; `border-slate-300` (inputs) →
  `dark:border-slate-600`.
- **Ink**: `text-slate-900` → `dark:text-slate-100`; `slate-700/600` →
  `dark:text-slate-300/200`; meta `slate-500/400` → `dark:text-slate-400/500`.
- **Hover**: `hover:bg-slate-100` → `dark:hover:bg-slate-800` (surface) or
  `dark:hover:bg-slate-700` (raised).
- **Honey is light, so it does NOT flip**: keep `bg-brand-400 text-slate-900`
  CTAs and `bg-brand-100 text-slate-900` selections exactly — dark ink on honey
  stays correct. Brand text on dark may brighten one step (`brand-700` →
  `dark:text-brand-400`).
- **Status tints**: `bg-green-100 text-green-800` →
  `dark:bg-green-950/50 dark:text-green-300` (same shape for red/amber). The
  custom `brand` ramp stops at 900 — use `brand-900/30`, never `brand-950`.

## Typography

One family: **Plus Jakarta Sans Variable** (self-hosted via Fontsource — no
font CDN). Fixed rem scale: page title `text-2xl–3xl extrabold tracking-tight`,
section headings `text-lg bold tracking-tight`, body `text-sm/base`, meta
`text-xs`. Tabular numerals in tables. Wordmark: `ausleihBAR` (plain ink
extrabold; the pun is carried by case, no decoration).

## Components

- **Buttons**: pill (`rounded-full`). Primary = `bg-brand-400 text-slate-900
  font-bold hover:bg-brand-500`; quiet = border `slate-300` + `hover:bg-slate-100`;
  destructive stays red text/links. Icon buttons are 40×40 circles.
- **Tiles** (sections/pools, image-led): `rounded-2xl border slate-200`,
  image well matches the admin crop ratio (sections/categories 4:3, pools
  16:9), text below; hover = lift −2px + `border-brand-400` + faint shadow +
  image scale 1.04.
- **Row cards** (products, sets): same chrome as tiles, 64px thumb
  (`rounded-xl`), chevron that slides toward honey on hover.
- **Calendars**: selected day = `border-brand-500 bg-brand-100`; availability
  numbers stay green/red; closed days greyed.
- **Menus/popovers**: `rounded-xl border slate-200 shadow-lg/5`, `animate-fade-up`,
  2.5-padding rows, check mark in `brand-600` for the active option.
- **Empty states**: emoji in a `brand-50` rounded square + one friendly line.
- **Loading**: small spin ring (`border-t-brand-500`), centered.

## Motion

150–250 ms, `ease-out-quart`, state-driven only: hover lift/scale, cart-badge
pop on count change, menu fade-up, one staggered entrance on the landing-page
pool list. Everything honors `prefers-reduced-motion` (global kill switch in
`index.css`).

## Accessibility (WCAG 2.1 AA / BITV-oriented)

Global `:focus-visible` ring (`brand-600`, offset 2), skip link, `<html lang>`
follows i18n, labelled icon buttons (cart count in the accessible name), touch
targets ≥40px, text contrast ≥4.5:1 incl. meta text, status conveyed with text
not color alone.

## Layout

Single column `max-w-3xl`, mobile-first at 390px; grids `grid-cols-2`
(sm:3) for tiles, `sm:grid-cols-2` for row cards. Header: logo · search
(expandable below `sm`) · area switcher (lenders/admins only) · language globe
· cart · account — cart always directly beside the avatar.
