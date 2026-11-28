// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useMemo, useState } from "react";
import type { LocationScope } from "./overviewFilter";

/** What the location picker needs of a floor (overview or `/desks/floors/`). */
export interface FloorLike {
  id: number;
  name: string;
  position?: number;
  building_id: number | null;
  /** Building code ("" without a building). */
  building: string;
  building_description: string;
}

const key = (pool: number) => `desks.floor.${pool}`;

function read(pool: number): number | null {
  try {
    const v = Number(window.localStorage.getItem(key(pool)));
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

/** Remember the floor last used in a department (picked or booked). */
export function rememberFloor(pool: number, floorId: number) {
  try {
    window.localStorage.setItem(key(pool), String(floorId));
  } catch {
    // Private mode / blocked storage: the choice just isn't kept.
  }
}

/**
 * The floor to show: the one last used in this department (picked on any
 * desk page or booked on the Book page), else `fallback` (the floor of the
 * latest own booking), else the first. `choose` switches and remembers;
 * `show` switches for this page only (e.g. the floor of a linked place).
 */
export function useRememberedFloor(
  pool: number,
  floors: { id: number }[] | null | undefined,
  fallback?: number | null,
) {
  const [chosen, setChosen] = useState<number | null>(() => read(pool));
  useEffect(() => setChosen(read(pool)), [pool]);
  const has = (id: number | null | undefined) => id != null && !!floors?.some((f) => f.id === id);
  const floorId = has(chosen) ? chosen : has(fallback) ? fallback! : (floors?.[0]?.id ?? null);
  const choose = useCallback(
    (id: number) => {
      setChosen(id);
      rememberFloor(pool, id);
    },
    [pool],
  );
  return [floorId, choose, setChosen] as const;
}

/** Stored scope: "all", "b<building id>" ("bnone" = floors without a
 *  building) or a floor id. */
type StoredScope = "all" | { building: number | null } | number;

function readScope(pool: number): StoredScope | null {
  try {
    const raw = window.localStorage.getItem(key(pool));
    if (raw === "all") return "all";
    if (raw === "bnone") return { building: null };
    if (raw?.startsWith("b")) {
      const id = Number(raw.slice(1));
      return Number.isInteger(id) && id > 0 ? { building: id } : null;
    }
    const v = Number(raw);
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

const toWish = (s: LocationScope): StoredScope =>
  s.floorId !== "all" ? s.floorId : s.buildingId === "all" ? "all" : { building: s.buildingId };

function storeScope(pool: number, scope: LocationScope) {
  const raw =
    scope.floorId !== "all"
      ? String(scope.floorId)
      : scope.buildingId === "all"
        ? "all"
        : `b${scope.buildingId ?? "none"}`;
  try {
    window.localStorage.setItem(key(pool), raw);
  } catch {
    // Private mode / blocked storage: the choice just isn't kept.
  }
}

/** Turns a wish into a scope the pool's floors allow: an unknown floor or
 *  building falls back to `fallback` (else the first floor); "all" or a
 *  building with a single floor becomes that floor. */
function resolveScope(
  wish: StoredScope | null,
  floors: FloorLike[],
  fallback: number | null | undefined,
): LocationScope | null {
  if (floors.length === 0) return null;
  const floorScope = (f: FloorLike): LocationScope => ({ buildingId: f.building_id, floorId: f.id });
  const fallbackFloor = floors.find((f) => f.id === fallback) ?? floors[0];
  if (wish === "all") return floors.length === 1 ? floorScope(floors[0]) : { buildingId: "all", floorId: "all" };
  if (typeof wish === "object" && wish !== null) {
    const inBuilding = floors.filter((f) => f.building_id === wish.building);
    if (inBuilding.length === 1) return floorScope(inBuilding[0]);
    if (inBuilding.length > 1) return { buildingId: wish.building, floorId: "all" };
    return floorScope(fallbackFloor);
  }
  return floorScope(floors.find((f) => f.id === wish) ?? fallbackFloor);
}

/**
 * Building / floor scope of the overview, remembered per department in the
 * same key as the floor (`desks.floor.<pool>`; old floor ids keep working).
 * Unknown or stale values fall back like `useRememberedFloor`. `choose`
 * switches and remembers; `show` switches for this page only (a room link).
 * The scope is null while the floors are unknown or there are none.
 */
export function useRememberedScope(
  pool: number,
  floors: FloorLike[] | null | undefined,
  fallback?: number | null,
) {
  const [wish, setWish] = useState<StoredScope | null>(() => readScope(pool));
  useEffect(() => setWish(readScope(pool)), [pool]);
  const scope = useMemo(() => resolveScope(wish, floors ?? [], fallback), [wish, floors, fallback]);
  const choose = useCallback(
    (s: LocationScope) => {
      setWish(toWish(s));
      storeScope(pool, s);
    },
    [pool],
  );
  const show = useCallback((s: LocationScope) => setWish(toWish(s)), []);
  return [scope, choose, show] as const;
}

/** A place as the text search sees it. */
export interface SearchablePlace {
  name: string;
  room: string;
  floor: string;
  floor_id: number;
  building: string;
  features: number[];
}

/**
 * Text search over places of every building and floor: place, room, floor,
 * building code and description, equipment. `term` is lower-cased already.
 */
export function matchesPlace(
  p: SearchablePlace,
  term: string,
  floors: Map<number, FloorLike>,
  featureNames: (ids: number[]) => string[],
): boolean {
  const f = floors.get(p.floor_id);
  return [p.name, p.room, p.floor, p.building, f?.building_description ?? "", ...featureNames(p.features)].some(
    (s) => s.toLocaleLowerCase().includes(term),
  );
}
