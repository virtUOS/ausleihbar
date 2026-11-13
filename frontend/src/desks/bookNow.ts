// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
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

/** The "Book now" button handler: books, toasts (incl. the absence warning)
 *  and goes to "My reservations". `booking` is the id being booked. */
export function useBookNow(pool: number) {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const [booking, setBooking] = useState<number | null>(null);

  async function bookNow(place: FreeNowPlace) {
    setBooking(place.id);
    try {
      const res = await bookFreeNow(pool, place);
      toast.success(t("Booked."));
      if (res.warnings.includes("absent")) {
        toast.warning(t("You are marked absent on this day. The booking was still made."));
      }
      navigate("/desks/mine");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBooking(null);
    }
  }
  return { booking, bookNow };
}
