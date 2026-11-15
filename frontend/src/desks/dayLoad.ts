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

/** Core hours of the two halves (clipped to the hours the place is open). */
export const MORNING: [number, number] = [8, 13];
export const AFTERNOON: [number, number] = [13, 18];

const TAKEN = new Set(["booked", "potentially_free", "checked_in"]);

function half(hours: OverviewHour[], [from, to]: [number, number]): HalfLoad | null {
  const open = hours.filter((h) => h.hour >= from && h.hour < to && h.state !== "closed");
  if (open.length === 0) return null;
  const taken = open.filter((h) => TAKEN.has(h.state)).length;
  return taken === 0 ? "free" : taken === open.length ? "full" : "part";
}

/** Morning / afternoon load of a place's day (null: closed in that half). */
export function dayLoad(hours: OverviewHour[]): DayLoad {
  return { morning: half(hours, MORNING), afternoon: half(hours, AFTERNOON) };
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
