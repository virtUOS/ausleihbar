// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { stateMeta } from "./placeStates";
import { primaryBtn } from "./formStyles";
import type { MeetingRoomDay } from "../types";
import { pad2 } from "../weekdays";

const pad = (h: number) => `${pad2(h)}:00`;

/** Booking from the timeline: the day and its bookable hours. */
export interface TimelineBooking {
  day: string;
  closed: number[];
  /** First hour that may still be booked (today: the current hour); null
   *  when the whole day is past. */
  minHour: number | null;
  onBooked: () => void;
}

/** A meeting room's day as a timeline. With `booking` (and a room the viewer
 *  may book) free hours can be selected — tap the start and the end hour or
 *  drag across them, like the hourly booking of the lending — and booked. */
export function MeetingTimeline({
  room,
  open,
  booking,
}: {
  room: MeetingRoomDay;
  open: [number, number] | null;
  booking?: TimelineBooking;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  let from = open ? open[0] : 6;
  let to = open ? open[1] : 20;
  for (const r of room.reservations) {
    from = Math.min(from, r.start_hour);
    to = Math.max(to, r.end_hour);
  }
  const span = Math.max(to - from, 1);
  const cols = Array.from({ length: span }, (_, i) => from + i);
  const pct = (h: number) => `${((h - from) / span) * 100}%`;

  const selectable =
    !!booking && room.bookable && !!open && booking.minHour !== null;
  const free = (h: number) =>
    selectable &&
    h >= open![0] &&
    h < open![1] &&
    h >= booking!.minHour! &&
    !booking!.closed.includes(h) &&
    !room.reservations.some((r) => r.start_hour <= h && h < r.end_hour);
  const allFree = (a: number, b: number) => {
    for (let h = Math.min(a, b); h <= Math.max(a, b); h++) if (!free(h)) return false;
    return true;
  };

  // Selected hours [lo, hi] (inclusive); hi null while picking the end.
  const [lo, setLo] = useState<number | null>(null);
  const [hi, setHi] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const anchor = useRef<number | null>(null);
  const dragged = useRef(false);

  // A new day or new reservations drop a selection that no longer fits.
  useEffect(() => {
    if (lo !== null && !allFree(lo, hi ?? lo)) {
      setLo(null);
      setHi(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room, booking?.day, booking?.minHour]);

  useEffect(() => {
    const up = () => (anchor.current = null);
    window.addEventListener("pointerup", up);
    return () => window.removeEventListener("pointerup", up);
  }, []);

  function setRange(a: number, b: number) {
    setLo(Math.min(a, b));
    setHi(Math.max(a, b) === Math.min(a, b) ? null : Math.max(a, b));
  }
  function tap(h: number) {
    if (lo === null || hi !== null) {
      setLo(h);
      setHi(null);
    } else if (h > lo && allFree(lo, h)) {
      setHi(h);
    } else if (h === lo) {
      setLo(null);
    } else {
      setLo(h);
    }
  }
  function onDown(h: number) {
    anchor.current = h;
    dragged.current = false;
  }
  function onEnter(h: number) {
    if (anchor.current === null || !allFree(anchor.current, h)) return;
    dragged.current = true;
    setRange(anchor.current, h);
  }
  function onUp(h: number) {
    if (anchor.current === null) return;
    if (dragged.current) {
      if (allFree(anchor.current, h)) setRange(anchor.current, h);
    } else {
      tap(h);
    }
    anchor.current = null;
  }

  const start = lo;
  const end = lo === null ? null : (hi ?? lo) + 1;

  async function book() {
    if (!booking || start === null || end === null) return;
    setBusy(true);
    try {
      const res = await desksApi.book({
        place_ids: [room.id],
        day: booking.day,
        start_hour: start,
        end_hour: end,
      });
      toast.success(t("Booked {{name}}, {{from}}–{{to}}.", { name: room.name, from: pad(start), to: pad(end) }));
      if (res.warnings.includes("absent")) {
        toast.warning(t("You are marked absent on this day. The booking was still made."));
      }
      setLo(null);
      setHi(null);
      booking.onBooked();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      booking.onBooked();
    } finally {
      setBusy(false);
    }
  }

  const more =
    booking && start !== null && end !== null
      ? `/desks/book?${new URLSearchParams({
          place: String(room.id),
          kind: "meeting_room",
          day: booking.day,
          start: String(start),
          end: String(end),
        })}`
      : null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2">
        <p className="font-medium text-slate-900 dark:text-slate-100">{room.name}</p>
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {[room.floor, room.room].filter(Boolean).join(" · ")}
          {room.capacity ? ` · ${t("{{count}} seats", { count: room.capacity })}` : ""}
        </p>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[560px]">
          <div className="relative h-5 text-[11px] text-slate-600 dark:text-slate-300" aria-hidden>
            {cols.map((h) => (
              <span key={h} className="absolute" style={{ left: pct(h) }}>
                {h}
              </span>
            ))}
          </div>
          <div className="relative h-16 select-none rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
            {cols.slice(1).map((h) => (
              <span
                key={h}
                aria-hidden
                className="absolute inset-y-0 border-l border-slate-200 dark:border-slate-700"
                style={{ left: pct(h) }}
              />
            ))}
            {selectable && (
              <div role="group" aria-label={t("Choose hours for {{name}}", { name: room.name })}>
                {cols.filter(free).map((h) => {
                  const on = start !== null && end !== null && h >= start && h < end;
                  return (
                    <button
                      key={h}
                      type="button"
                      aria-pressed={on}
                      aria-label={`${pad(h)}–${pad(h + 1)}`}
                      onPointerDown={() => onDown(h)}
                      onPointerEnter={() => onEnter(h)}
                      onPointerUp={() => onUp(h)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          tap(h);
                        }
                      }}
                      className={`absolute inset-y-0 border-0 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-900 dark:focus-visible:ring-slate-100 ${
                        on ? "bg-brand-400 dark:bg-brand-500" : "hover:bg-brand-100 dark:hover:bg-brand-900/40"
                      }`}
                      style={{ left: pct(h), width: `${100 / span}%` }}
                    />
                  );
                })}
              </div>
            )}
            {room.reservations.map((r) => (
              <div
                key={r.id}
                aria-hidden
                className={`absolute inset-y-1 overflow-hidden rounded-md border px-1.5 py-0.5 text-[11px] leading-tight ${stateMeta(r.state).pill} ${r.mine ? "ring-2 ring-brand-500" : ""}`}
                style={{ left: pct(r.start_hour), width: `calc(${((r.end_hour - r.start_hour) / span) * 100}% - 2px)` }}
                title={[`${pad(r.start_hour)}–${pad(r.end_hour)}`, r.holder ?? t("Person (hidden)"), r.comment].filter(Boolean).join(" · ")}
              >
                <span className="block truncate font-semibold">
                  {r.mine ? t("Your reservation") : (r.holder ?? t("Person (hidden)"))}
                </span>
                {r.comment && <span className="block truncate">{r.comment}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
      {room.reservations.length === 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">{t("No reservations this day.")}</p>
      )}
      {booking && open && booking.minHour !== null && !room.bookable && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">{t("You cannot book this room.")}</p>
      )}
      {selectable && start === null && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          {t("Tap the free hours (start and end) or drag across them to book.")}
        </p>
      )}
      {selectable && start !== null && end !== null && (
        <div className="mt-3 flex flex-wrap items-center gap-2" aria-live="polite">
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {pad(start)}–{pad(end)}
          </span>
          <button type="button" onClick={book} disabled={busy} className={primaryBtn}>
            {t("Book")}
          </button>
          {more && (
            <Link
              to={more}
              className="inline-flex min-h-[44px] items-center px-2 text-sm font-medium text-slate-700 underline underline-offset-2 hover:text-slate-900 dark:text-slate-200 dark:hover:text-white"
            >
              {t("More options")}
            </Link>
          )}
          <button
            type="button"
            aria-label={t("Clear selection")}
            onClick={() => {
              setLo(null);
              setHi(null);
            }}
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <X aria-hidden className="h-5 w-5" />
          </button>
        </div>
      )}
      <ul className="sr-only">
        {room.reservations.map((r) => (
          <li key={r.id}>
            {[`${pad(r.start_hour)}–${pad(r.end_hour)}: ${r.holder ?? t("Person (hidden)")}`, r.comment].filter(Boolean).join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}
