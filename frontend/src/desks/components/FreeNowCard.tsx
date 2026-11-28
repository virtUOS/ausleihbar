// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { DoorOpen, LampDesk } from "lucide-react";
import { berlinNow } from "../time";
import { pad2 } from "../weekdays";
import { freeEndHour, quickRanges, useBookNow, useShowBooked } from "../bookNow";
import { PlaceTimeline, type TimelineEntry } from "./PlaceTimeline";
import { BookLaterLink } from "./BookLaterLink";
import type { DepartmentDay, FreeNowPlace, PlaceKind } from "../types";

/** Current Berlin hour; `onChange` runs when a new full hour starts (checked
 *  every 30 s and when the tab becomes visible again). */
export function useNowHour(onChange?: () => void): number {
  const [nowHour, setNowHour] = useState(() => berlinNow().hour);
  const changed = useRef(onChange);
  changed.current = onChange;
  useEffect(() => {
    let last = berlinNow().hour;
    const tick = () => {
      const h = berlinNow().hour;
      if (h === last) return;
      last = h;
      setNowHour(h);
      changed.current?.();
    };
    const id = window.setInterval(tick, 30_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, []);
  return nowHour;
}

const quickBtn =
  "min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50";

/**
 * One place with today's occupancy, as on "Jetzt frei": icon, name and
 * `details`, quick bookings from now (when `free` — the place as the
 * free-now list reports it), with `later` a "Book later" link to the Book
 * page, `action` at the end of the row (heart, remove), and below the day's
 * timeline (select hours to book).
 */
export function FreeNowCard({
  pool,
  place,
  details,
  entry,
  day,
  nowHour,
  free,
  action,
  later = false,
  onFailed,
}: {
  pool: number;
  place: { id: number; name: string; kind: PlaceKind };
  details: ReactNode;
  entry: TimelineEntry | undefined;
  day: DepartmentDay | null | undefined;
  nowHour: number;
  free: FreeNowPlace | null;
  action: ReactNode;
  /** Also offer booking ahead (Book page with the place preselected). */
  later?: boolean;
  /** After a failed booking (taken meanwhile): reload. */
  onFailed: () => void;
}) {
  const { t } = useTranslation();
  const { booking, bookNow } = useBookNow(pool, onFailed);
  const showBooked = useShowBooked();
  const Icon = place.kind === "meeting_room" ? DoorOpen : LampDesk;
  const closeHour = day?.open_hours?.[1] ?? null;
  const end = free ? freeEndHour(free, closeHour) : null;
  const timeline = !!entry && !!day?.open_hours;

  let quick: ReactNode = null;
  if (free) {
    quick =
      end === null ? (
        // Day not loaded (or failed): book to the end of the free stretch.
        <button type="button" disabled={booking !== null} onClick={() => bookNow(free.id, null)} className={quickBtn}>
          {t("Book now")}
        </button>
      ) : (
        quickRanges(nowHour, end).map((q) => (
          <button
            key={q.hours ?? "rest"}
            type="button"
            disabled={booking !== null}
            onClick={() => bookNow(free.id, end, q.hours)}
            className={quickBtn}
          >
            {q.hours
              ? t("{{value}} h", { value: q.hours })
              : t("until {{time}}", { time: `${pad2(q.end)}:00` })}
            {/* The visible text starts the name (WCAG 2.5.3), the range follows. */}
            <span className="sr-only">
              {" "}
              (
              {t("Book {{name}} {{from}}–{{to}}", {
                name: place.name,
                from: `${pad2(nowHour)}:00`,
                to: `${pad2(q.end)}:00`,
              })}
              )
            </span>
          </button>
        ))
      );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      {/* Phones: icon, name, action on top, quick bookings below;
          wider: quick bookings move up next to the action. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Icon aria-hidden className="h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400" />
        <div className="min-w-0 flex-1">{details}</div>
        {(quick || later) && (
          <div className="order-last flex basis-full flex-wrap items-center gap-2 sm:order-none sm:basis-auto">
            {quick && <span className="text-sm text-slate-600 dark:text-slate-300">{t("Book from now:")}</span>}
            {quick}
            {later && <BookLaterLink pool={pool} place={place} />}
          </div>
        )}
        {action}
      </div>
      {timeline && (
        <div className="mt-2">
          <PlaceTimeline
            entry={entry!}
            open={day!.open_hours!}
            bare
            slim
            booking={{
              day: day!.day,
              closed: day!.closed_hours,
              minHour: nowHour,
              onBooked: (res) => (res ? showBooked(res) : onFailed()),
            }}
          />
        </div>
      )}
    </div>
  );
}
