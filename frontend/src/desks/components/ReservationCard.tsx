// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeftRight, LampDesk, DoorOpen, MapPinCheck, MoveRight, Repeat, Trash2 } from "lucide-react";
import { useFetch } from "../../useFetch";
import { formatDayWithWeekday, formatTime } from "../../dates";
import { ErrorBox, Loading } from "../../components/Status";
import { desksApi } from "../api";
import type { Reservation } from "../types";
import { pad2 } from "../weekdays";
import { canCheckIn, useMinuteNow } from "../checkIn";
import {
  activeLateUntil,
  btnIcon,
  btnPrimary,
  LateControls,
  useReservationActions,
  type Run,
} from "./reservationActions";

type Panel = null | "move" | "swap";

function Badge({ tone, children }: { tone: "green" | "sky" | "grey" | "brand"; children: string }) {
  const cls = {
    brand: "bg-brand-100 text-brand-900 dark:bg-brand-900/50 dark:text-brand-100",
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    sky: "bg-sky-100 text-sky-900 dark:bg-sky-950/60 dark:text-sky-200",
    grey: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  }[tone];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{children}</span>;
}

interface Props {
  reservation: Reservation;
  onChanged: () => void;
  /** Show the date on the card (lists that are not grouped by day). */
  showDay?: boolean;
  /** Just booked (the user came here from booking it): highlighted. */
  justBooked?: boolean;
  /** Rendered inside a series group: the series badge/link is redundant. */
  inSeries?: boolean;
}

/** One own reservation with its status badges and icon actions (check in,
 *  late, move, swap request, delete) and, for desks, the people in the room. */
export function ReservationCard({ reservation: r, onChanged, showDay, justBooked = false, inSeries = false }: Props) {
  const { t } = useTranslation();
  const [panel, setPanel] = useState<Panel>(null);

  // Time-based UI (check-in window, late chips) re-evaluates every minute and
  // when the tab becomes visible again.
  const now = useMinuteNow();
  const actions = useReservationActions(r, now, () => onChanged());
  const { busy, run } = actions;
  const start = new Date(r.start).getTime();
  const end = new Date(r.end).getTime();
  const ended = end <= now;
  const started = start <= now;
  const checkInOpen = canCheckIn(r, now);
  const canLater = !r.checked_in_at && !ended;
  const lateUntil = activeLateUntil(r, now);
  const Icon = r.place.kind === "meeting_room" ? DoorOpen : LampDesk;

  const nb = r.place.kind === "desk" ? (r.neighbours ?? []) : [];
  const hiddenCount = nb.filter((n) => n === null).length;
  const neighbourNames =
    nb.length > 0
      ? [
          ...nb.filter((n): n is string => n !== null),
          ...(hiddenCount > 0 ? [t("+{{count}} more", { count: hiddenCount })] : []),
        ].join(", ")
      : null;

  const toggle = (p: Panel) => {
    actions.late.setOpen(false);
    setPanel(panel === p ? null : p);
  };

  return (
    <li
      data-just-booked={justBooked || undefined}
      className={`rounded-xl border bg-white px-3 py-2 dark:bg-slate-900 ${
        justBooked
          ? "border-brand-500 ring-2 ring-brand-500/40 dark:border-brand-400 dark:ring-brand-400/30"
          : "border-slate-200 dark:border-slate-800"
      }`}
    >
      <div className="flex flex-wrap items-start gap-3">
        <Icon aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400" />
        <div className="min-w-0 grow basis-48">
          <p className="font-medium text-slate-900 dark:text-slate-100">
            {r.place.name}
            <span className="ml-2 text-sm font-normal text-slate-600 dark:text-slate-300">
              {showDay && `${formatDayWithWeekday(r.day)}, `}
              {pad2(r.start_hour)}:00–{pad2(r.end_hour)}:00
            </span>
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {[r.place.building, r.place.floor, r.place.room].filter(Boolean).join(" · ")}
          </p>
          {neighbourNames && (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {t("With you in the room: {{names}}", { names: neighbourNames })}
            </p>
          )}
          {r.comment && (
            <p className="break-words text-sm italic text-slate-700 dark:text-slate-200">{r.comment}</p>
          )}
          <div className="mt-1 flex flex-wrap gap-1.5 empty:hidden">
            {justBooked && <Badge tone="brand">{t("Just booked")}</Badge>}
            {r.checked_in_at && <Badge tone="green">{t("Checked in")}</Badge>}
            {r.potentially_free_at && !r.checked_in_at && <Badge tone="sky">{t("Potentially free")}</Badge>}
            {lateUntil && !r.checked_in_at && (
              <Badge tone="grey">{t("Late until {{time}}", { time: formatTime(lateUntil) })}</Badge>
            )}
            {r.series_id !== null &&
              !inSeries &&
              (showDay ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                  <Repeat aria-hidden className="h-3 w-3" />
                  {t("Series")}
                </span>
              ) : (
                <Link
                  to={`/desks/series/${r.series_id}`}
                  className="relative inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700 underline-offset-2 before:absolute before:-inset-x-2 before:-inset-y-3 before:content-[''] hover:underline dark:bg-slate-800 dark:text-slate-200"
                >
                  <Repeat aria-hidden className="h-3 w-3" />
                  {t("Series")}
                </Link>
              ))}
          </div>
        </div>
        <div className={`flex flex-wrap items-center justify-start gap-1.5 ${actions.late.open ? "basis-full" : ""}`}>
          {checkInOpen && (
            <button
              type="button"
              disabled={busy}
              onClick={actions.checkIn}
              aria-label={t("Check in")}
              title={t("Check in")}
              className={`${btnPrimary} inline-flex h-11 w-11 items-center justify-center !px-0`}
            >
              <MapPinCheck aria-hidden className="h-5 w-5" />
            </button>
          )}
          {canLater && <LateControls actions={actions} onToggle={() => setPanel(null)} />}
          {!ended && (
            <button
              type="button"
              aria-expanded={panel === "move"}
              aria-label={t("Move")}
              title={t("Move")}
              onClick={() => toggle("move")}
              className={btnIcon}
            >
              <MoveRight aria-hidden className="h-5 w-5" />
            </button>
          )}
          {!started && (
            <button
              type="button"
              aria-expanded={panel === "swap"}
              aria-label={t("Request swap")}
              title={t("Request swap")}
              onClick={() => toggle("swap")}
              className={btnIcon}
            >
              <ArrowLeftRight aria-hidden className="h-5 w-5" />
            </button>
          )}
          {!ended && (
            <button
              type="button"
              disabled={busy}
              aria-label={t("Delete")}
              title={t("Delete")}
              onClick={actions.remove}
              className={btnIcon}
            >
              <Trash2 aria-hidden className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>

      {panel === "move" && <MovePanel r={r} busy={busy} run={run} />}
      {panel === "swap" && <SwapPanel r={r} busy={busy} run={run} />}
    </li>
  );
}

export type { Run };

/** Free places for the same hours (same kind, the holder's rights), grouped
 *  by room; one tap moves. Shared by the holder's card and admin actions. */
export function MovePanel({ r, busy, run }: { r: Reservation; busy: boolean; run: Run }) {
  const { t } = useTranslation();
  const { data, loading, error } = useFetch(() => desksApi.moveTargets(r.id), [r.id]);
  // Two taps (Move, place): moving is reversible, so no extra confirmation.
  const move = (id: number) => run(() => desksApi.move(r.id, id), t("Moved."));
  const places = (data ?? []).filter((p) => p.id !== r.place.id);
  // Whole department, grouped by room (own room first).
  const whereOf = (p: { building?: string; floor: string; room: string }) =>
    [p.building, p.floor, p.room].filter(Boolean).join(" · ");
  const own = whereOf(r.place);
  const byRoom = new Map<string, typeof places>();
  for (const p of places) byRoom.set(whereOf(p), [...(byRoom.get(whereOf(p)) ?? []), p]);
  const groups = [...byRoom.entries()].sort(
    ([a], [b]) => Number(b === own) - Number(a === own) || a.localeCompare(b),
  );
  return (
    <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
      <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">
        {t("Free places for the same time")}
      </p>
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && places.length === 0 && (
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("No other place is free.")}</p>
      )}
      {groups.map(([where, list]) => (
        <div key={where} className="mb-3">
          <p className="mb-1 text-xs font-semibold text-slate-600 dark:text-slate-300">{where}</p>
          <ul className="space-y-2">
            {list.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => move(p.id)}
                  className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-left hover:border-brand-400 dark:border-slate-700"
                >
                  <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                    {p.name}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

interface SwapCandidate {
  reservationId: number;
  placeName: string;
  where: string;
  holder: string | null;
  start: number;
  end: number;
}

function SwapPanel({ r, busy, run }: { r: Reservation; busy: boolean; run: Run }) {
  const { t } = useTranslation();
  const pool = r.place.pool;
  // The overview of the reservation's own department lists only that
  // department's places, so every candidate belongs to it (the backend
  // refuses swaps across departments).
  const { data, loading, error } = useFetch(
    () => (pool ? desksApi.overview(pool, r.day) : Promise.resolve(null)),
    [r.id],
  );
  const candidates: SwapCandidate[] = [];
  if (data) {
    const seen = new Set<number>();
    for (const floor of data.floors) {
      for (const p of floor.places) {
        if (p.kind !== r.place.kind || p.id === r.place.id) continue;
        // Swap requests need people access (not via "Alle Angemeldeten" alone).
        if (p.people_visible === false) continue;
        for (const h of p.hours) {
          if (h.hour < r.start_hour || h.hour >= r.end_hour) continue;
          if (h.reservation_id === null || h.mine || seen.has(h.reservation_id)) continue;
          seen.add(h.reservation_id);
          const same = p.hours.filter((x) => x.reservation_id === h.reservation_id);
          candidates.push({
            reservationId: h.reservation_id,
            placeName: p.name,
            where: [floor.building, floor.name, floor.rooms.find((x) => x.id === p.room_id)?.name]
              .filter(Boolean)
              .join(" · "),
            holder: h.holder,
            start: Math.min(...same.map((x) => x.hour)),
            end: Math.max(...same.map((x) => x.hour)) + 1,
          });
        }
      }
    }
  }
  return (
    <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
      <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">
        {t("Booked places of the same kind at an overlapping time")}
      </p>
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && candidates.length === 0 && (
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("There is nothing to swap with.")}</p>
      )}
      <ul className="space-y-2">
        {candidates.map((c) => (
          <li key={c.reservationId}>
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => desksApi.requestSwap(r.id, c.reservationId), t("Swap request sent."))}
              className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-left hover:border-brand-400 dark:border-slate-700"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                  {c.placeName} · {pad2(c.start)}:00–{pad2(c.end)}:00
                </span>
                <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                  {[c.where, c.holder ?? t("Person (hidden)")].filter(Boolean).join(" · ")}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
