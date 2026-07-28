// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Shared helpers for the lending-desk views.
import { api } from "./api";
import type { LendingType, ManagedBooking } from "./types";

export interface BookingAction {
  label: string;
  run: (id: number) => Promise<unknown>;
}

// The single next action available for each booking status.
export const ACTION: Record<string, BookingAction> = {
  pending: { label: "Confirm", run: api.confirmBooking },
  confirmed: { label: "Hand out", run: api.handoutBooking },
  handed_out: { label: "Return", run: api.returnBooking },
};

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
    const d = (x: Date) => x.toLocaleDateString();
    if (!lastDay || d(lastDay) === d(startDate)) return d(startDate);
    return `${d(startDate)} – ${d(lastDay)}`;
  }
  if (!end) return new Date(start).toLocaleString();
  const fmt = (s: string) => new Date(s).toLocaleString();
  return `${fmt(start)} → ${fmt(end)}`;
}

const localDate = (iso: string) => new Date(iso).toLocaleDateString("en-CA");

/** A pickup whose day has passed (confirmed) or a return past its due date. */
export function isOverdue(booking: ManagedBooking, today: string): boolean {
  if (booking.status === "confirmed") {
    const starts = booking.items.map((i) => i.start).filter(Boolean) as string[];
    return starts.length > 0 && localDate(starts.reduce((a, c) => (a < c ? a : c))) < today;
  }
  if (booking.status === "handed_out") {
    const ends = booking.items.map((i) => i.end).filter(Boolean) as string[];
    return ends.length > 0 && localDate(ends.reduce((a, c) => (a > c ? a : c))) < today;
  }
  return false;
}
