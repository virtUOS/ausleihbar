// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import i18n from "../i18n";

/** Print presets: an A4 sheet of tiles, or one label per page for roll printers. */
export interface LabelFormat {
  id: string;
  name: string;
  mode: "sheet" | "label";
  w: number; // label width in mm
  h: number; // label height in mm
}

// Each format drives the printed page size (an A4 sheet of tiles, or one label
// per page) through a static stylesheet: `public/print/qr-label-<id>.css` (label
// mode) or `qr-sheet.css` (sheet mode). Keep them in sync with `w`/`h` below —
// they are static files because an inline `<style>` is not allowed by the CSP
// (#44).
export const FORMATS: LabelFormat[] = [
  // Brother P-touch CUBE Pro PT-E920BT — continuous TZe tape (36 / 24 mm).
  // The tape width is fixed (the label height, which also sizes the QR); the
  // length is cut per label, so `w` is a sensible fixed length you can adjust.
  {
    id: "ptouch36",
    name: i18n.t("Tape · 36 mm (Brother P-touch PT-E920BT)"),
    mode: "label",
    w: 70,
    h: 36,
  },
  {
    id: "ptouch24",
    name: i18n.t("Tape · 24 mm (Brother P-touch PT-E920BT)"),
    mode: "label",
    w: 54,
    h: 24,
  },
  { id: "a4", name: i18n.t("A4 sheet (cut out)"), mode: "sheet", w: 62, h: 30 },
  {
    id: "roll62",
    name: i18n.t("Roll · 62 mm endless (Brother QL)"),
    mode: "label",
    w: 62,
    h: 30,
  },
  {
    id: "roll62x29",
    name: i18n.t("Roll · 62 × 29 mm (Brother DK-11209)"),
    mode: "label",
    w: 62,
    h: 29,
  },
  {
    id: "roll90x29",
    name: i18n.t("Roll · 90 × 29 mm (Brother DK-11201)"),
    mode: "label",
    w: 90,
    h: 29,
  },
  {
    id: "dymo89x36",
    name: i18n.t("Roll · 89 × 36 mm (DYMO 99012)"),
    mode: "label",
    w: 89,
    h: 36,
  },
];

/** Static print stylesheet of a format (page size + label layout). */
export const printStylesheet = (format: LabelFormat): string =>
  format.mode === "label" ? `/print/qr-label-${format.id}.css` : "/print/qr-sheet.css";
