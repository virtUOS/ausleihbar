// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Armchair, DoorOpen, Repeat, Users } from "lucide-react";
import { useFetch } from "../../useFetch";
import { formatDayWithWeekday, formatTime } from "../../dates";
import { ErrorBox, Loading } from "../../components/Status";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Reservation } from "../types";
import { pad2 } from "../weekdays";

const CHECK_IN_LEAD_MS = 15 * 60 * 1000;
const LATER_STEPS = [
  { minutes: 30, label: "+30 min" },
  { minutes: 60, label: "+1 h" },
  { minutes: 120, label: "+2 h" },
  { minutes: 180, label: "+3 h" },
];

type Panel = null | "later" | "move" | "swap" | "neighbours";

const btn =
  "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";
const btnPrimary =
  "min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50";

function Badge({ tone, children }: { tone: "green" | "amber" | "grey"; children: string }) {
  const cls = {
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    amber: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
    grey: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  }[tone];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{children}</span>;
}

interface Props {
  reservation: Reservation;
  onChanged: () => void;
  /** Show the date on the card (lists that are not grouped by day). */
  showDay?: boolean;
}

/** One own reservation with its status badges and actions (check in, later,
 *  release, move, swap request, "with you in the room"). */
export function ReservationCard({ reservation: r, onChanged, showDay }: Props) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const [panel, setPanel] = useState<Panel>(null);
  const [busy, setBusy] = useState(false);

  // Time-based UI (check-in window, late chips) re-evaluates every minute and
  // when the tab becomes visible again.
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
  const start = new Date(r.start).getTime();
  const end = new Date(r.end).getTime();
  const ended = end <= now;
  const started = start <= now;
  const canCheckIn = !r.checked_in_at && now >= start - CHECK_IN_LEAD_MS && now < end;
  const canLater = !r.checked_in_at && !ended;
  // Arrival offsets count from the start once it lies ahead.
  const base = Math.max(now, start);
  const lateUntil = r.late_until && new Date(r.late_until).getTime() > now ? r.late_until : null;
  const Icon = r.place.kind === "meeting_room" ? DoorOpen : Armchair;

  async function run(action: () => Promise<unknown>, success: string, after?: () => void) {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      setPanel(null);
      after?.();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function release() {
    const ok = await confirm({
      message: t("Release {{place}}? The place becomes free for others.", { place: r.place.name }),
      confirmLabel: t("Release"),
      cancelLabel: t("Keep"),
      danger: true,
    });
    if (!ok) return;
    await run(() => desksApi.cancelReservation(r.id), t("Reservation released."));
  }

  function later(minutes: number) {
    const until = new Date(Math.min(Math.max(Date.now(), start) + minutes * 60_000, end));
    return run(() => desksApi.later(r.id, until.toISOString()), t("Noted. We keep your place."));
  }

  // Chips up to the first one that reaches the end (it is capped there).
  const laterSteps: typeof LATER_STEPS = [];
  for (const s of LATER_STEPS) {
    laterSteps.push(s);
    if (base + s.minutes * 60_000 >= end) break;
  }

  const toggle = (p: Panel) => setPanel(panel === p ? null : p);

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-slate-900 dark:text-slate-100">{r.place.name}</p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {showDay && `${formatDayWithWeekday(r.day)}, `}
            {pad2(r.start_hour)}:00–{pad2(r.end_hour)}:00
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {[r.place.building, r.place.floor, r.place.room].filter(Boolean).join(" · ")}
          </p>
          {r.comment && (
            <p className="mt-1 break-words text-sm italic text-slate-700 dark:text-slate-200">
              {r.comment}
            </p>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {r.checked_in_at && <Badge tone="green">{t("Checked in")}</Badge>}
        {r.potentially_free_at && !r.checked_in_at && <Badge tone="amber">{t("Potentially free")}</Badge>}
        {lateUntil && !r.checked_in_at && (
          <Badge tone="grey">{t("Late until {{time}}", { time: formatTime(lateUntil) })}</Badge>
        )}
        {r.series_id !== null &&
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

      <div className="mt-3 flex flex-wrap gap-2">
        {canCheckIn && (
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => desksApi.checkIn(r.id), t("Checked in."))}
            className={btnPrimary}
          >
            {t("Check in")}
          </button>
        )}
        {canLater && (
          <button type="button" aria-expanded={panel === "later"} onClick={() => toggle("later")} className={btn}>
            {t("I'll be late")}
          </button>
        )}
        {!ended && (
          <button type="button" aria-expanded={panel === "move"} onClick={() => toggle("move")} className={btn}>
            {t("Move")}
          </button>
        )}
        {!started && (
          <button type="button" aria-expanded={panel === "swap"} onClick={() => toggle("swap")} className={btn}>
            {t("Request swap")}
          </button>
        )}
        {r.place.kind === "desk" && (
          <button
            type="button"
            aria-expanded={panel === "neighbours"}
            onClick={() => toggle("neighbours")}
            className={`${btn} inline-flex items-center gap-1.5`}
          >
            <Users aria-hidden className="h-4 w-4" />
            {t("With you in the room")}
          </button>
        )}
        {!ended && (
          <button type="button" disabled={busy} onClick={release} className={btn}>
            {t("Release")}
          </button>
        )}
      </div>

      {panel === "later" && (
        <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
          <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">{t("I will arrive in about…")}</p>
          <div className="flex flex-wrap gap-2">
            {laterSteps.map((s) => (
              <button key={s.minutes} type="button" disabled={busy} onClick={() => later(s.minutes)} className={btn}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {panel === "move" && <MovePanel r={r} busy={busy} run={run} />}
      {panel === "swap" && <SwapPanel r={r} busy={busy} run={run} />}
      {panel === "neighbours" && <NeighboursPanel r={r} />}
    </li>
  );
}

export type Run = (action: () => Promise<unknown>, success: string, after?: () => void) => Promise<void>;

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

function NeighboursPanel({ r }: { r: Reservation }) {
  const { t } = useTranslation();
  const { data, loading, error } = useFetch(() => desksApi.neighbours(r.id), [r.id]);
  return (
    <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("Nobody else is booked in this room.")}</p>
      )}
      {data && data.length > 0 && (
        <ul className="list-disc pl-5 text-sm text-slate-800 dark:text-slate-100">
          {data.map((name, i) => (
            <li key={i}>{name ?? t("Person (hidden)")}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
