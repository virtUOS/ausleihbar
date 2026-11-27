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

/** Quick bookings from now: 4 and 8 hours, cut to the free stretch (then
 *  "until …" once). `hours` undefined = to the end of the stretch. */
export function quickRanges(now: number, end: number): { hours?: number; end: number }[] {
  if (end - now <= 4) return [{ end }];
  if (end - now < 8) return [{ hours: 4, end: now + 4 }, { end }];
  return [{ hours: 4, end: now + 4 }, { hours: 8, end: now + 8 }];
}

/** One-tap booking of a place that is free now: from the current full hour
 *  for `hours` hours (default: to `freeEnd`, the end of the free stretch),
 *  never past that stretch. `freeEnd` null: the day's closing hour is looked up. */
export async function bookFreeNow(
  pool: number,
  placeId: number,
  freeEnd: number | null,
  hours?: number,
): Promise<BookResult> {
  const today = berlinNow();
  let end = freeEnd;
  if (end === null) {
    const h = await desksApi.hours(pool, today.date);
    end = h.open ? h.open[1] : today.hour + 1;
  }
  if (hours) end = Math.min(end, today.hour + hours);
  if (end <= today.hour) end = today.hour + 1;
  return desksApi.book({
    place_ids: [placeId],
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

  async function bookNow(placeId: number, freeEnd: number | null, hours?: number) {
    setBooking(placeId);
    try {
      const res = await bookFreeNow(pool, placeId, freeEnd, hours);
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
