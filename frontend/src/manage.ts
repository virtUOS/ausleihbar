// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Shared helpers for the lending-desk views.
import { formatDate, formatDateTime } from "./dates";
import type { LendingType } from "./types";

export function todayIso(): string {
  return new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local time
}

export function shiftDate(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + delta);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

/**
 * Format a booking period for display. A day booking shows an inclusive date
 * range — the stored `end` is the exclusive following midnight, so the last
 * booked day is one tick earlier (single day → one date, no time). An hourly
 * booking shows real date+time.
 */
export function formatPeriod(
  start: string | null,
  end: string | null,
  lendingType?: LendingType,
): string {
  if (!start) return "—";
  if (lendingType === "days") {
    const startDate = new Date(start);
    const lastDay = end ? new Date(new Date(end).getTime() - 1) : null;
    const d = (x: Date) => formatDate(x.toISOString());
    if (!lastDay || d(lastDay) === d(startDate)) return d(startDate);
    return `${d(startDate)} – ${d(lastDay)}`;
  }
  if (!end) return formatDateTime(start);
  return `${formatDateTime(start)} → ${formatDateTime(end)}`;
}

const DAY_POOL_KEY = "ausleihbar.manage.dayPool";

/** The day overview's remembered pool filter (null = all pools). */
export function readDayPool(): number | null {
  try {
    const v = localStorage.getItem(DAY_POOL_KEY);
    return v ? Number(v) || null : null;
  } catch {
    return null;
  }
}

/** Remember (or clear with null) the day overview's pool filter. */
export function storeDayPool(id: number | null): void {
  try {
    if (id === null) localStorage.removeItem(DAY_POOL_KEY);
    else localStorage.setItem(DAY_POOL_KEY, String(id));
  } catch {
    /* storage unavailable — filter just isn't remembered */
  }
}
