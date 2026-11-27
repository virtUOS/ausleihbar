// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { DrawState } from "./components/placeStates";
import { dayLoad } from "./dayLoad";
import type { OverviewFloor, OverviewPlace, PlaceKind } from "./types";

export function stateAt(p: OverviewPlace, hour: number | null): DrawState {
  if (hour === null) return "closed";
  return p.hours.find((h) => h.hour === hour)?.state ?? "closed";
}

/** The plan symbol of a whole day: booked once neither half has a block of
 *  four bookable hours left (`dayLoad`), possibly free when some taken hours
 *  may come free (the half rings tell morning from afternoon). */
export function dayState(p: OverviewPlace): DrawState {
  const open = p.hours.filter((h) => h.state !== "closed");
  if (open.length === 0) return "closed";
  const { morning, afternoon } = dayLoad(p.hours);
  if ([morning, afternoon].some((half) => half !== null && half !== "full")) return "free";
  return open.some((h) => h.state === "potentially_free") ? "potentially_free" : "booked";
}

export interface PlaceFilter {
  onlyFree: boolean;
  onlyFavorites: boolean;
  kind: PlaceKind | "";
  features: number[];
  roomId: number | null;
}

export const EMPTY_FILTER: PlaceFilter = {
  onlyFree: false,
  onlyFavorites: false,
  kind: "",
  features: [],
  roomId: null,
};

/** Number of active filter criteria (the room has its own chip, not counted). */
export function activeFilterCount(f: PlaceFilter): number {
  return (f.onlyFree ? 1 : 0) + (f.onlyFavorites ? 1 : 0) + (f.kind !== "" ? 1 : 0) + f.features.length;
}

/** Free right now (`nowHour` = current hour when the shown day is today) or,
 *  for another day, free at some point of the day. */
export function isFreeForFilter(p: OverviewPlace, nowHour: number | null): boolean {
  return p.bookable && (nowHour !== null ? stateAt(p, nowHour) === "free" : dayState(p) === "free");
}

export function matchesFilter(
  p: OverviewPlace,
  f: PlaceFilter,
  ctx: { nowHour: number | null; favorites: Set<number> },
): boolean {
  if (f.roomId !== null && p.room_id !== f.roomId) return false;
  if (f.onlyFree && !isFreeForFilter(p, ctx.nowHour)) return false;
  if (f.onlyFavorites && !ctx.favorites.has(p.id)) return false;
  if (f.kind !== "" && p.kind !== f.kind) return false;
  return f.features.every((id) => p.features.includes(id));
}

/** Building (null = floors without one) and floor selection; "all" = no limit. */
export type LocationScope = { buildingId: number | null | "all"; floorId: number | "all" };

export function floorsInScope(floors: OverviewFloor[], scope: LocationScope): OverviewFloor[] {
  return floors.filter(
    (fl) =>
      (scope.buildingId === "all" || fl.building_id === scope.buildingId) &&
      (scope.floorId === "all" || fl.id === scope.floorId),
  );
}

/** First hour at or after `nowHour` that is no longer free (the place is free
 *  until then); `closeHour` when it stays free to the end. null when not free
 *  at `nowHour`. */
export function freeUntilHour(
  p: OverviewPlace,
  nowHour: number,
  closeHour: number | null,
): number | null {
  if (stateAt(p, nowHour) !== "free") return null;
  const last = p.hours.reduce((m, h) => Math.max(m, h.hour), nowHour);
  for (let h = nowHour + 1; h <= last; h++) {
    if (stateAt(p, h) !== "free") return h;
  }
  return closeHour;
}
