// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useState } from "react";

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
 * The floor to show: the one last used in this department (any desk page,
 * also set when booking), else `fallback` (e.g. the floor of the latest own
 * booking), else the first. `choose` switches and remembers.
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
  return [floorId, choose] as const;
}
