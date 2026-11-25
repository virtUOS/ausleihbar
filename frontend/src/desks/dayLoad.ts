// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import type { OverviewHour } from "./types";

/** How much of a half day is booked. */
export type HalfLoad = "free" | "part" | "full";
export interface DayLoad {
  morning: HalfLoad | null;
  afternoon: HalfLoad | null;
}

/** Afternoon starts at this hour; each half spans the open hours on its side. */
export const NOON = 13;
/** A half counts as fully booked once no block of this many consecutive
 *  bookable hours is left in it (fewer when the half is shorter). */
export const MIN_FREE_RUN = 4;

const TAKEN = new Set(["booked", "potentially_free", "checked_in"]);

function half(hours: OverviewHour[], inHalf: (hour: number) => boolean): HalfLoad | null {
  const open = hours
    .filter((h) => inHalf(h.hour) && h.state !== "closed")
    .sort((a, b) => a.hour - b.hour);
  if (open.length === 0) return null;
  if (!open.some((h) => TAKEN.has(h.state))) return "free";
  let run = 0;
  let longest = 0;
  let prev: number | null = null;
  for (const h of open) {
    run = h.state === "free" ? (prev !== null && h.hour === prev + 1 ? run + 1 : 1) : 0;
    prev = h.state === "free" ? h.hour : null;
    longest = Math.max(longest, run);
  }
  return longest >= Math.min(MIN_FREE_RUN, open.length) ? "part" : "full";
}

/** Morning / afternoon load of a place's day (null: closed in that half). */
export function dayLoad(hours: OverviewHour[]): DayLoad {
  return {
    morning: half(hours, (hour) => hour < NOON),
    afternoon: half(hours, (hour) => hour >= NOON),
  };
}

function halfText(t: TFunction, load: HalfLoad): string {
  return load === "full" ? t("booked") : load === "part" ? t("partly booked") : t("free");
}

/** Spoken form, e.g. "morning booked, afternoon free". */
export function dayLoadText(t: TFunction, load: DayLoad): string {
  const parts = [];
  if (load.morning) parts.push(t("morning {{state}}", { state: halfText(t, load.morning) }));
  if (load.afternoon) parts.push(t("afternoon {{state}}", { state: halfText(t, load.afternoon) }));
  return parts.join(", ");
}
