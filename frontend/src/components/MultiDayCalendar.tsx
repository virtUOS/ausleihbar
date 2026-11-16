// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import type { MouseEvent, PointerEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { MonthCalendar } from "./MonthCalendar";
import {
  addRange,
  rangesContain,
  removeRange,
  toggleDay,
  type DayRange,
} from "../dayRanges";

interface MultiDayCalendarProps {
  /** The selected days as inclusive ranges (normalized on every change). */
  value: DayRange[];
  onChange: (next: DayRange[]) => void;
  /** Selectable bounds (ISO, inclusive); days outside are disabled and every
   *  emitted range is clamped to them. Month navigation stays within them. */
  minDay: string;
  maxDay: string;
  /** Further days that can't be clicked (combined with the bounds). A drag
   *  or Shift-extend across such a day still covers it. */
  isDisabled?: (iso: string) => boolean;
  /** Days greyed but still interactive (see `MonthCalendar`). */
  isMuted?: (iso: string) => boolean;
  /** Content below each day number. */
  renderDay?: (iso: string) => ReactNode;
  /** Months shown. Default: two side by side from `sm` up, one below. */
  months?: 1 | 2;
}

/** A pointer drag in progress (mouse/pen only — on touch a drag would fight
 *  page scrolling, so touch is taps only). */
interface Drag {
  start: string;
  current: string;
  /** The pointer reached another day; only then is this a drag at all. */
  moved: boolean;
  /** Cmd/Ctrl or "Single days": add to (or remove from) the selection
   *  instead of replacing it. */
  additive: boolean;
  /** An additive drag that starts on a selected day removes its span. */
  startSelected: boolean;
}

const monthIndex = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1;

/** Select several days or day ranges in a month calendar.
 *
 *  - Click/tap A, then B: the selection becomes A–B (replacing it). The first
 *    tap already emits the single day A via `onChange`, so it shows selected.
 *  - Drag A→B (mouse/pen): the same, emitted once on release.
 *  - Cmd/Ctrl-click: toggle one day. Cmd/Ctrl-drag: add the span, or remove
 *    it when the drag started on a selected day.
 *  - Shift-click: extend from the last clicked day (the anchor) to the clicked
 *    day, merging with the range that holds the anchor. Without an anchor it
 *    acts like a plain click.
 *  - "Single days" toggle: plain clicks/taps/drags behave like Cmd/Ctrl — the
 *    way to toggle days on touch.
 *  Keyboard: days are buttons; Enter/Space act as a click with the held
 *  modifier keys. */
export function MultiDayCalendar({
  value,
  onChange,
  minDay,
  maxDay,
  isDisabled,
  isMuted,
  renderDay,
  months,
}: MultiDayCalendarProps) {
  const { t } = useTranslation();
  const minIdx = monthIndex(minDay);
  const maxIdx = Math.max(minIdx, monthIndex(maxDay));
  const clampIdx = (idx: number) => Math.min(Math.max(idx, minIdx), maxIdx);

  /** Shown (first) month as `year * 12 + month`. */
  const [view, setView] = useState(() => clampIdx(monthIndex(value[0]?.start ?? minDay)));
  const [singleDays, setSingleDays] = useState(false);
  /** First tap of a plain A→B selection, waiting for B. */
  const [pending, setPending] = useState<string | null>(null);
  /** The selection as it would be after the running drag (display only). */
  const [preview, setPreview] = useState<DayRange[] | null>(null);
  const anchor = useRef<string | null>(null);
  const drag = useRef<Drag | null>(null);
  /** Ends the window listeners of the running drag. */
  const dragListeners = useRef<AbortController | null>(null);
  /** Set after a drag released on another day, so the click a browser may
   *  still fire there isn't applied a second time. */
  const suppressClick = useRef(false);

  useEffect(() => () => dragListeners.current?.abort(), []);

  /** The days a–b (either order) cut to the bounds, or null if none remain. */
  function clamp(a: string, b: string): [string, string] | null {
    const lo = a <= b ? a : b;
    const hi = a <= b ? b : a;
    const s = lo < minDay ? minDay : lo;
    const e = hi > maxDay ? maxDay : hi;
    return s <= e ? [s, e] : null;
  }

  function dragResult(d: Drag): DayRange[] {
    const span = clamp(d.start, d.current);
    if (!span) return value;
    if (!d.additive) return [{ start: span[0], end: span[1] }];
    return d.startSelected ? removeRange(value, ...span) : addRange(value, ...span);
  }

  /** A pending first tap only counts while the selection is still exactly
   *  that day (the parent may have changed it meanwhile). */
  const pendingDay =
    pending && value.length === 1 && value[0].start === pending && value[0].end === pending
      ? pending
      : null;

  function handleClick(iso: string, e: MouseEvent<HTMLButtonElement>) {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    if (e.shiftKey && anchor.current) {
      const span = clamp(anchor.current, iso);
      if (span) onChange(addRange(value, ...span));
      setPending(null);
      return;
    }
    anchor.current = iso;
    if (singleDays || e.metaKey || e.ctrlKey) {
      onChange(toggleDay(value, iso));
      setPending(null);
    } else if (pendingDay) {
      const span = clamp(pendingDay, iso);
      if (span) onChange([{ start: span[0], end: span[1] }]);
      setPending(null);
    } else {
      onChange([{ start: iso, end: iso }]);
      setPending(iso);
    }
  }

  function endDrag(apply: boolean) {
    const d = drag.current;
    drag.current = null;
    dragListeners.current?.abort();
    dragListeners.current = null;
    setPreview(null);
    if (!d?.moved || !apply) return;
    onChange(dragResult(d));
    anchor.current = d.current;
    setPending(null);
    // Some browsers fire no click when press and release land on different
    // buttons — clear the flag after this event so it can't eat a later click.
    suppressClick.current = true;
    setTimeout(() => {
      suppressClick.current = false;
    }, 0);
  }

  function handlePointerDown(iso: string, e: PointerEvent<HTMLButtonElement>) {
    suppressClick.current = false;
    if (e.pointerType === "touch" || e.button !== 0) return;
    dragListeners.current?.abort();
    drag.current = {
      start: iso,
      current: iso,
      moved: false,
      additive: singleDays || e.metaKey || e.ctrlKey,
      startSelected: rangesContain(value, iso),
    };
    // Released anywhere (outside the grid, on a disabled day) ends the drag.
    const ctrl = new AbortController();
    dragListeners.current = ctrl;
    window.addEventListener("pointerup", () => endDrag(true), { signal: ctrl.signal });
    window.addEventListener("pointercancel", () => endDrag(false), { signal: ctrl.signal });
  }

  function handlePointerEnter(iso: string) {
    const d = drag.current;
    if (!d || iso < minDay || iso > maxDay || isDisabled?.(iso)) return;
    if (!d.moved && iso === d.start) return;
    d.moved = true;
    d.current = iso;
    setPreview(dragResult(d));
  }

  const shown = preview ?? value;
  const calendarProps = {
    onDayClick: handleClick,
    onDayPointerDown: handlePointerDown,
    onDayPointerEnter: handlePointerEnter,
    isSelected: (iso: string) => rangesContain(shown, iso),
    isDisabled: (iso: string) => iso < minDay || iso > maxDay || (isDisabled?.(iso) ?? false),
    isMuted,
    renderDay,
  };
  const at = (idx: number) => ({ year: Math.floor(idx / 12), month: idx % 12 });

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          aria-pressed={singleDays}
          onClick={() => {
            setSingleDays(!singleDays);
            setPending(null);
          }}
          className={`min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
            singleDays
              ? "border-brand-500 bg-brand-100 text-slate-900"
              : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          }`}
        >
          {t("Single days")}
        </button>
        <button
          type="button"
          disabled={value.length === 0}
          onClick={() => {
            onChange([]);
            setPending(null);
            anchor.current = null;
          }}
          className="min-h-[44px] rounded-full px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {t("Clear selected days")}
        </button>
      </div>
      <div className={months === 1 ? "" : "grid gap-6 sm:grid-cols-2"}>
        <MonthCalendar
          {...at(view)}
          onMonthChange={(y, m) => setView(clampIdx(y * 12 + m))}
          {...calendarProps}
        />
        {months !== 1 && (
          <div className={months === 2 ? "" : "hidden sm:block"}>
            <MonthCalendar
              {...at(view + 1)}
              onMonthChange={(y, m) => setView(clampIdx(y * 12 + m - 1))}
              {...calendarProps}
            />
          </div>
        )}
      </div>
    </div>
  );
}
