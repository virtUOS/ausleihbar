// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useFetch } from "../useFetch";
import { desksApi } from "./api";

/** Days in `from..to` closed by blocks (public holidays, department
 *  closures), for greying them out in calendars. Empty while loading or on
 *  an error — the backend refuses bookings on closed hours anyway. Without
 *  `pool` only system-wide blocks count. */
export function useClosedDays(from: string, to: string, pool?: number | null): Set<string> {
  const { data } = useFetch(() => desksApi.closedDays(from, to, pool), [from, to, pool]);
  return useMemo(() => new Set(data?.days ?? []), [data]);
}
