// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useFetch } from "../useFetch";
import { desksApi } from "./api";
import { addDays } from "./weekdays";

/** The endpoint answers at most this many days after `from` per call. */
const MAX_SPAN = 400;

/** Days in `from..to` closed by blocks (public holidays, department
 *  closures), for greying them out in calendars. Empty while loading or on
 *  an error — the backend refuses bookings on closed hours anyway. Without
 *  `pool` only system-wide blocks count. Longer spans are asked for in
 *  chunks the endpoint accepts. */
export function useClosedDays(from: string, to: string, pool?: number | null): Set<string> {
  const { data } = useFetch(() => {
    const calls: Promise<{ days: string[] }>[] = [];
    for (let start = from; start <= to; start = addDays(start, MAX_SPAN + 1)) {
      const end = addDays(start, MAX_SPAN);
      calls.push(desksApi.closedDays(start, end < to ? end : to, pool));
    }
    return Promise.all(calls).then((rows) => rows.flatMap((r) => r.days));
  }, [from, to, pool]);
  return useMemo(() => new Set(data ?? []), [data]);
}
