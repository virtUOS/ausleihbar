// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";

const STORAGE_KEY = "desks.pool";

function stored(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? Number(raw) || null : null;
  } catch {
    return null;
  }
}

export interface DeskPool {
  id: number;
  name: string;
}

/** The departments the user may book in (`whoami.desk_pool_ids`) with their
 *  names, and the remembered current one. */
export function useDeskPools() {
  const { user } = useAuth();
  const ids = user?.desk_pool_ids ?? [];
  const adminIds = user?.desk_admin_pool_ids ?? [];
  const assistantIds = user?.desk_assistant_pool_ids ?? [];
  const names = new Map((user?.desk_pools ?? []).map((p) => [p.id, p.name]));
  const pools: DeskPool[] = ids.map((id) => ({ id, name: names.get(id) ?? `#${id}` }));
  const [chosen, setChosen] = useState<number | null>(stored);
  const current = ids.includes(chosen ?? -1) ? (chosen as number) : (ids[0] ?? null);
  const select = useCallback((id: number) => {
    setChosen(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      // not persisted (private mode) — selection still holds for this page
    }
  }, []);
  // `?pool=<id>` (links from outside the area, e.g. the favourites page)
  // switches to that department when the user may book there.
  const [params] = useSearchParams();
  const fromUrl = Number(params.get("pool"));
  useEffect(() => {
    if (fromUrl && ids.includes(fromUrl) && fromUrl !== chosen) select(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromUrl]);
  return {
    pools,
    current,
    select,
    isAdmin: current !== null && adminIds.includes(current),
    /** Assistants (and admins): absences and booking for others. */
    isAssistant: current !== null && assistantIds.includes(current),
  };
}
