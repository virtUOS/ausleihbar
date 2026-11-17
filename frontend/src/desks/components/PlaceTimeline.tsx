// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DoorOpen, X } from "lucide-react";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { primaryBtn } from "./formStyles";
import type { BookResult, HourState, MeetingRoomDay, OverviewPlace, PlaceKind } from "../types";
import { pad2 } from "../weekdays";

const pad = (h: number) => `${pad2(h)}:00`;

/** One block of a timeline (a reservation, or a fixed owner's day). */
export interface TimelineBlock {
  key: string;
  start_hour: number;
  end_hour: number;
  state: HourState;
  holder: string | null;
  comment?: string;
  mine: boolean;
}

/** What a timeline shows: a place and its blocks of the day. */
export interface TimelineEntry {
  id: number;
  name: string;
  kind: PlaceKind;
  /** Second line (full layout): floor, room, seats. */
  subtitle?: string;
  /** Seats of a meeting room (compact rows show them). */
  capacity?: number | null;
  bookable: boolean;
  blocks: TimelineBlock[];
}

export function meetingRoomEntry(m: MeetingRoomDay, subtitle: string): TimelineEntry {
  return {
    id: m.id,
    name: m.name,
    kind: "meeting_room",
    subtitle,
    capacity: m.capacity,
    bookable: m.bookable,
    blocks: m.reservations.map((r) => ({ ...r, key: String(r.id) })),
  };
}

/** A place's hours grouped into blocks (consecutive hours of one
 *  reservation, or of the fixed owner). */
export function placeEntry(p: OverviewPlace): TimelineEntry {
  const blocks: TimelineBlock[] = [];
  for (const h of p.hours) {
    if (h.state === "free" || h.state === "closed") continue;
    const last = blocks[blocks.length - 1];
    const same =
      last &&
      last.end_hour === h.hour &&
      last.state === h.state &&
      last.holder === h.holder &&
      last.mine === h.mine &&
      last.key === `${p.id}-${h.reservation_id ?? "fixed"}-${last.start_hour}`;
    if (same) last.end_hour = h.hour + 1;
    else
      blocks.push({
        key: `${p.id}-${h.reservation_id ?? "fixed"}-${h.hour}`,
        start_hour: h.hour,
        end_hour: h.hour + 1,
        state: h.state,
        holder: h.holder,
        mine: h.mine,
      });
  }
  return { id: p.id, name: p.name, kind: p.kind, capacity: p.capacity, bookable: p.bookable, blocks };
}

/** Booking from the timeline: the day and its bookable hours. */
export interface TimelineBooking {
  day: string;
  closed: number[];
  /** First hour that may still be booked (today: the current hour); null
   *  when the whole day is past. */
  minHour: number | null;
  /** After a booking attempt; `res` is set when it succeeded. */
  onBooked: (res?: BookResult) => void;
}

// Others' bookings honey, "possibly free" light blue, own ones green
// (dashed while not checked in and possibly free).
export const BLOCK_BOOKED =
  "border-brand-600 bg-brand-100 text-slate-900 dark:border-brand-400 dark:bg-brand-900/40 dark:text-brand-100";
export const BLOCK_POSSIBLY_FREE =
  "border-sky-600 bg-sky-100 text-sky-950 dark:border-sky-400 dark:bg-sky-950/60 dark:text-sky-100";
export const BLOCK_MINE =
  "border-green-700 bg-green-100 text-green-900 dark:border-green-400 dark:bg-green-950/60 dark:text-green-100";
function blockClass(b: TimelineBlock): string {
  if (b.mine) return `${BLOCK_MINE} ${b.state === "potentially_free" ? "border-dashed" : ""}`;
  return b.state === "potentially_free" ? BLOCK_POSSIBLY_FREE : BLOCK_BOOKED;
}

/** The hour labels of a compact timeline group, aligned with the bars. */
export function TimelineAxis({ open }: { open: [number, number] }) {
  const span = Math.max(open[1] - open[0], 1);
  const cols = Array.from({ length: span }, (_, i) => open[0] + i);
  return (
    <div aria-hidden className="grid grid-cols-[6.5rem_1fr] gap-2 sm:grid-cols-[9rem_1fr]">
      <span />
      <div className="relative h-4 text-[11px] text-slate-600 dark:text-slate-300">
        {cols.map((h, i) => (
          <span
            key={h}
            className={`absolute ${i % 2 ? "hidden sm:inline" : ""}`}
            style={{ left: `${((h - open[0]) / span) * 100}%` }}
          >
            {h}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Controlled hour selection (instead of booking from the timeline). */
export interface TimelineSelect {
  /** Selected hours as [start, end) or none. */
  value: { start: number; end: number } | null;
  onChange: (r: { start: number; end: number } | null) => void;
  /** Per hour: on how many of `total` days it is taken (shaded, still
   *  selectable — these are not reservations of this timeline). */
  counts?: Record<number, number>;
  total?: number;
}

/** Hatching of hours taken on some of several days. */
const TAKEN_HATCH = {
  backgroundImage:
    "repeating-linear-gradient(135deg, rgba(190, 18, 60, 0.3) 0 3px, transparent 3px 7px)",
};

/** A place's day as a timeline. Free hours of a place the viewer may book
 *  can be selected — tap the start and the end hour, or drag across them
 *  with the mouse, like the hourly booking of the lending — and booked,
 *  with an optional text. `compact`: one slim row (name | bar) for lists,
 *  hour labels from a shared `TimelineAxis`. */
export function PlaceTimeline({
  entry,
  open,
  booking,
  compact = false,
  bare = false,
  slim = false,
  onOpen,
  onBlockClick,
  focusKey,
  select,
}: {
  entry: TimelineEntry;
  open: [number, number] | null;
  booking?: TimelineBooking;
  compact?: boolean;
  /** Full layout without its own card and title (inside the place sheet). */
  bare?: boolean;
  /** With `bare`: a slim bar without the hint lines (list rows). */
  slim?: boolean;
  /** Compact rows: the name opens the place's details. */
  onOpen?: (id: number) => void;
  /** Blocks become buttons (e.g. to show who booked and what can be done). */
  onBlockClick?: (b: TimelineBlock) => void;
  /** Key of the block shown as focused. */
  focusKey?: string | null;
  /** Controlled select mode: hours are chosen via `select` and no booking
   *  footer is shown (`booking.onBooked` is never called). `booking` only
   *  supplies `closed` and `minHour` (without it: no closed hours, minHour 0). */
  select?: TimelineSelect;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  let from = open ? open[0] : 6;
  let to = open ? open[1] : 20;
  if (!compact) {
    for (const b of entry.blocks) {
      from = Math.min(from, b.start_hour);
      to = Math.max(to, b.end_hour);
    }
  }
  const span = Math.max(to - from, 1);
  const cols = Array.from({ length: span }, (_, i) => from + i);
  const pct = (h: number) => `${((Math.min(Math.max(h, from), to) - from) / span) * 100}%`;
  const closed = booking?.closed ?? [];

  const minHour = booking ? booking.minHour : select ? 0 : null;
  const selectable = (!!booking || !!select) && entry.bookable && !!open && minHour !== null;
  const free = (h: number) =>
    selectable &&
    h >= open![0] &&
    h < open![1] &&
    h >= minHour! &&
    !closed.includes(h) &&
    !entry.blocks.some((b) => b.start_hour <= h && h < b.end_hour);
  const allFree = (a: number, b: number) => {
    for (let h = Math.min(a, b); h <= Math.max(a, b); h++) if (!free(h)) return false;
    return true;
  };

  // Selected hours [lo, hi] (inclusive); hi null while picking the end.
  const [loState, setLoState] = useState<number | null>(null);
  const [hiState, setHiState] = useState<number | null>(null);
  const lo = select ? (select.value?.start ?? null) : loState;
  const hi = select ? (select.value && select.value.end - 1 > select.value.start ? select.value.end - 1 : null) : hiState;
  function setSel(l: number | null, h: number | null) {
    if (select) select.onChange(l === null ? null : { start: l, end: (h ?? l) + 1 });
    else {
      setLoState(l);
      setHiState(h);
    }
  }
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");
  const anchor = useRef<number | null>(null);
  const dragged = useRef(false);

  // A new day or new reservations drop a selection that no longer fits.
  useEffect(() => {
    if (!select && lo !== null && !allFree(lo, hi ?? lo)) setSel(null, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry, booking?.day, booking?.minHour]);

  useEffect(() => {
    const up = () => (anchor.current = null);
    window.addEventListener("pointerup", up);
    return () => window.removeEventListener("pointerup", up);
  }, []);

  function clear() {
    setSel(null, null);
  }
  function setRange(a: number, b: number) {
    setSel(Math.min(a, b), Math.max(a, b) === Math.min(a, b) ? null : Math.max(a, b));
  }
  function tap(h: number) {
    if (lo === null || hi !== null) {
      setSel(h, null);
    } else if (h > lo && allFree(lo, h)) {
      setSel(lo, h);
    } else if (h === lo) {
      setSel(null, null);
    } else {
      setSel(h, null);
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
        place_ids: [entry.id],
        day: booking.day,
        start_hour: start,
        end_hour: end,
        comment: comment.trim(),
      });
      toast.success(t("Booked {{name}}, {{from}}–{{to}}.", { name: entry.name, from: pad(start), to: pad(end) }));
      if (res.warnings.includes("absent")) {
        toast.warning(t("You are marked absent on this day. The booking was still made."));
      }
      clear();
      setComment("");
      booking.onBooked(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      booking.onBooked();
    } finally {
      setBusy(false);
    }
  }

  const more =
    booking && !select && start !== null && end !== null
      ? `/desks/book?${new URLSearchParams({
          place: String(entry.id),
          kind: entry.kind,
          day: booking.day,
          start: String(start),
          end: String(end),
          ...(comment.trim() ? { comment: comment.trim() } : {}),
        })}`
      : null;

  const holderText = (b: TimelineBlock) => (b.mine ? t("Your reservation") : (b.holder ?? t("Booked")));

  const bar = (
    <div
      className={`relative select-none rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60 ${
        compact || slim ? "h-9" : "h-16"
      }`}
    >
      {cols.slice(1).map((h) => (
        <span
          key={h}
          aria-hidden
          className="absolute inset-y-0 border-l border-slate-200 dark:border-slate-700"
          style={{ left: pct(h) }}
        />
      ))}
      {closed
        .filter((h) => h >= from && h < to)
        .map((h) => (
          <span
            key={`c${h}`}
            aria-hidden
            className="absolute inset-y-0 bg-slate-200/80 dark:bg-slate-700/70"
            style={{ left: pct(h), width: `${100 / span}%` }}
          />
        ))}
      {selectable && (
        <div role="group" aria-label={t("Choose hours for {{name}}", { name: entry.name })}>
          {cols.filter(free).map((h) => {
            const on = start !== null && end !== null && h >= start && h < end;
            const taken = select?.counts?.[h] ?? 0;
            const takenLabel =
              taken > 0
                ? t("taken on {{count}} of {{total}} days", { count: taken, total: select?.total ?? taken })
                : null;
            return (
              <button
                key={h}
                type="button"
                aria-pressed={on}
                aria-label={`${pad(h)}–${pad(h + 1)}${takenLabel ? `, ${takenLabel}` : ""}`}
                title={takenLabel ?? undefined}
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
                  on ? "bg-slate-900/15 dark:bg-slate-100/20" : "hover:bg-slate-200/70 dark:hover:bg-slate-700/60"
                }`}
                style={{ left: pct(h), width: `${100 / span}%`, ...(takenLabel ? TAKEN_HATCH : {}) }}
              />
            );
          })}
        </div>
      )}
      {selectable && start !== null && end !== null && (
        // The selection as one frame across its hours.
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 rounded-md ring-2 ring-inset ring-slate-900 dark:ring-slate-100"
          style={{ left: pct(start), width: `calc(${pct(end)} - ${pct(start)})` }}
        />
      )}
      {entry.blocks.map((b) => {
        const cls = `absolute overflow-hidden rounded-md border px-1.5 text-left text-[11px] leading-tight ${
          compact || slim ? "inset-y-0.5 flex items-center" : "inset-y-1 py-0.5"
        } ${blockClass(b)} ${focusKey === b.key ? "ring-2 ring-slate-900 ring-offset-1 dark:ring-slate-100 dark:ring-offset-slate-900" : ""}`;
        const style = {
          left: pct(b.start_hour),
          width: `calc(${pct(b.end_hour)} - ${pct(b.start_hour)} - 2px)`,
        };
        const label = [`${pad(b.start_hour)}–${pad(b.end_hour)}`, holderText(b), b.comment].filter(Boolean).join(" · ");
        const body = (
          <>
            <span className="block truncate font-semibold">{holderText(b)}</span>
            {!compact && !slim && b.comment && <span className="block truncate">{b.comment}</span>}
          </>
        );
        return onBlockClick ? (
          <button
            key={b.key}
            type="button"
            onClick={() => onBlockClick(b)}
            aria-label={label}
            aria-pressed={focusKey !== undefined ? focusKey === b.key : undefined}
            title={label}
            className={`${cls} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 dark:focus-visible:ring-slate-100`}
            style={style}
          >
            {body}
          </button>
        ) : (
          <div key={b.key} aria-hidden className={cls} style={style} title={label}>
            {body}
          </div>
        );
      })}
    </div>
  );

  const selectionBar = !select && selectable && start !== null && end !== null && (
    <div className="mt-2 flex flex-wrap items-center gap-2" aria-live="polite">
      <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {compact ? `${entry.name} · ` : ""}
        {pad(start)}–{pad(end)}
      </span>
      <label className="min-w-0 flex-1 basis-48">
        <span className="sr-only">{t("Text (optional)")}</span>
        <input
          type="text"
          value={comment}
          maxLength={200}
          onChange={(e) => setComment(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !busy) book();
          }}
          placeholder={t("Text (optional), e.g. team meeting")}
          className="min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
      </label>
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
        onClick={clear}
        className="flex h-11 w-11 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        <X aria-hidden className="h-5 w-5" />
      </button>
    </div>
  );

  const srList = (
    <ul className="sr-only">
      {entry.blocks.map((b) => (
        <li key={b.key}>
          {[`${pad(b.start_hour)}–${pad(b.end_hour)}: ${holderText(b)}`, b.comment].filter(Boolean).join(", ")}
        </li>
      ))}
    </ul>
  );

  if (compact) {
    const meeting = entry.kind === "meeting_room";
    const name = (
      <>
        <span className="flex items-center gap-1.5">
          {meeting && <DoorOpen aria-hidden className="h-4 w-4 shrink-0 text-slate-700 dark:text-slate-200" />}
          <span className="truncate">{entry.name}</span>
        </span>
        {meeting && entry.capacity ? (
          <span className="block text-[11px] font-normal text-slate-600 dark:text-slate-300">
            {t("{{count}} seats", { count: entry.capacity })}
          </span>
        ) : null}
      </>
    );
    return (
      <li
        className={
          meeting
            ? "-mx-1.5 rounded-lg border border-slate-200 bg-slate-100/80 px-1.5 py-1 dark:border-slate-700 dark:bg-slate-800/70"
            : undefined
        }
      >
        <div className="grid grid-cols-[6.5rem_1fr] items-center gap-2 sm:grid-cols-[9rem_1fr]">
          {onOpen ? (
            <button
              type="button"
              onClick={() => onOpen(entry.id)}
              className={`min-h-[44px] min-w-0 rounded-md px-1 text-left text-sm text-slate-900 underline-offset-2 hover:underline dark:text-slate-100 ${meeting ? "font-bold" : "font-medium"}`}
              title={entry.name}
            >
              {name}
            </button>
          ) : (
            <span className="min-w-0 text-sm font-medium text-slate-900 dark:text-slate-100">{name}</span>
          )}
          {bar}
        </div>
        {selectionBar}
        {srList}
      </li>
    );
  }

  return (
    <div className={bare ? "" : "rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"}>
      {!bare && (
        <div className="mb-2">
          <p className="font-medium text-slate-900 dark:text-slate-100">{entry.name}</p>
          {entry.subtitle && <p className="text-xs text-slate-600 dark:text-slate-300">{entry.subtitle}</p>}
        </div>
      )}
      <div className={bare ? "" : "overflow-x-auto"}>
        <div className={bare ? "" : "min-w-[560px]"}>
          <div className="relative h-5 text-[11px] text-slate-600 dark:text-slate-300" aria-hidden>
            {cols.map((h, i) => (
              <span key={h} className={`absolute ${bare && i % 2 ? "hidden sm:inline" : ""}`} style={{ left: pct(h) }}>
                {h}
              </span>
            ))}
          </div>
          {bar}
        </div>
      </div>
      {!slim && entry.blocks.length === 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">{t("No reservations this day.")}</p>
      )}
      {booking && open && booking.minHour !== null && !entry.bookable && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          {entry.kind === "meeting_room" ? t("You cannot book this room.") : t("You cannot book this place.")}
        </p>
      )}
      {!slim && !select && selectable && start === null && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          {t("Tap the start and end hour to book, or drag across free hours with the mouse.")}
        </p>
      )}
      {selectionBar}
      {srList}
    </div>
  );
}
