// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import i18n from "../i18n";

/** Weekday name in the UI language; 0 = Monday … 6 = Sunday. */
export function weekdayName(d: number, width: "short" | "long" = "short"): string {
  // 2024-01-01 was a Monday.
  return new Date(2024, 0, 1 + d).toLocaleDateString(i18n.language, { weekday: width });
}

export const pad2 = (n: number) => String(n).padStart(2, "0");
export const isoOf = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
export const parseIso = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
};
/** 0 = Monday … 6 = Sunday of an ISO date. */
export const weekdayOf = (iso: string) => (parseIso(iso).getDay() + 6) % 7;
export function addDays(iso: string, n: number): string {
  const d = parseIso(iso);
  d.setDate(d.getDate() + n);
  return isoOf(d);
}
/** Calendar-month addition clamped to the month's end (like the backend). */
export function addMonths(iso: string, n: number): string {
  const d = parseIso(iso);
  const day = d.getDate();
  d.setDate(1);
  d.setMonth(d.getMonth() + n);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(day, last));
  return isoOf(d);
}
