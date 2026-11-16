// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { berlinNow, berlinParts } from "./time";
import type { BookResult, FreeNowPlace } from "./types";

/** Last hour (exclusive) of a free-now place's free stretch today: its
 *  `free_until`, else the day's closing hour (`closeHour`, if known). */
export function freeEndHour(place: FreeNowPlace, closeHour: number | null): number | null {
  const today = berlinNow();
  if (place.free_until) {
    const until = berlinParts(place.free_until);
    if (until.date === today.date) return until.hour;
  }
  return closeHour;
}

/** One-tap booking of a place that is free now: from the current full hour
 *  for `hours` hours (default: to the end of the free stretch), never past
 *  that stretch or the day's closing hour (`closeHour` when the caller knows
 *  it, else looked up). */
export async function bookFreeNow(
  pool: number,
  place: FreeNowPlace,
  hours?: number,
  closeHour: number | null = null,
): Promise<BookResult> {
  const today = berlinNow();
  let end = freeEndHour(place, closeHour);
  if (end === null) {
    const h = await desksApi.hours(pool, today.date);
    end = h.open ? h.open[1] : today.hour + 1;
  }
  if (hours) end = Math.min(end, today.hour + hours);
  if (end <= today.hour) end = today.hour + 1;
  return desksApi.book({
    place_ids: [place.id],
    day: today.date,
    start_hour: today.hour,
    end_hour: end,
  });
}

/** Go to "My reservations" with the new reservations highlighted. */
export function useShowBooked() {
  const navigate = useNavigate();
  return (res: BookResult) =>
    navigate("/desks/mine", { state: { booked: res.reservations.map((r) => r.id) } satisfies BookedState });
}

/** Navigation state of "My reservations": ids of the reservations just made. */
export interface BookedState {
  booked: number[];
}

/** The "Book now" button handler: books, toasts (incl. the absence warning)
 *  and goes to "My reservations". `booking` is the id being booked. */
export function useBookNow(pool: number, onFailed?: () => void) {
  const { t } = useTranslation();
  const toast = useToast();
  const showBooked = useShowBooked();
  const [booking, setBooking] = useState<number | null>(null);

  async function bookNow(place: FreeNowPlace, hours?: number, closeHour?: number | null) {
    setBooking(place.id);
    try {
      const res = await bookFreeNow(pool, place, hours, closeHour ?? null);
      toast.success(t("Booked."));
      if (res.warnings.includes("absent")) {
        toast.warning(t("You are marked absent on this day. The booking was still made."));
      }
      showBooked(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      onFailed?.();
    } finally {
      setBooking(null);
    }
  }
  return { booking, bookNow };
}
