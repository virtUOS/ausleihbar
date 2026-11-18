// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import type { Reservation } from "./types";

/** Check-in opens this long before a reservation starts. */
export const CHECK_IN_LEAD_MS = 15 * 60 * 1000;

/** Whether the reservation can be checked in at `now` (ms): not yet checked
 *  in, from 15 minutes before the start until the end. */
export function canCheckIn(r: Pick<Reservation, "start" | "end" | "checked_in_at">, now: number): boolean {
  const start = new Date(r.start).getTime();
  const end = new Date(r.end).getTime();
  return !r.checked_in_at && now >= start - CHECK_IN_LEAD_MS && now < end;
}

/** The current time in ms, refreshed every minute and when the tab becomes
 *  visible again. */
export function useMinuteNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const id = window.setInterval(tick, 60_000);
    const onVisible = () => document.visibilityState === "visible" && tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return now;
}
