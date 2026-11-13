// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { desksApi } from "./api";
import { berlinNow, berlinParts } from "./time";
import type { BookResult, FreeNowPlace } from "./types";

/** One-tap booking of a place that is free now: from the current full hour to
 *  the end of the free stretch (or the day's closing hour). */
export async function bookFreeNow(pool: number, place: FreeNowPlace): Promise<BookResult> {
  const today = berlinNow();
  let end = 24;
  if (place.free_until) {
    const until = berlinParts(place.free_until);
    end = until.date === today.date ? until.hour : 24;
  }
  if (end === 24) {
    const h = await desksApi.hours(pool, today.date);
    end = h.open ? h.open[1] : today.hour + 1;
  }
  if (end <= today.hour) end = today.hour + 1;
  return desksApi.book({
    place_ids: [place.id],
    day: today.date,
    start_hour: today.hour,
    end_hour: end,
  });
}
