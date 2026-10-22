// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Check, Minus, Plus } from "lucide-react";
import { api } from "../api";
import { durationRange, limitValue } from "../durations";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { setPoolScopeLocked } from "../poolScope";
import { ManageTabs } from "../components/ManageTabs";
import { GroupedProductPicker } from "../components/GroupedProductPicker";
import { OnsiteTag } from "../components/OnsiteTag";
import { SortToggle } from "../components/SortToggle";
import { useConfirm } from "../components/ConfirmDialog";
import { ErrorBox, Loading } from "../components/Status";
import { formatDate, formatDateTime } from "../dates";
import type {
  BorrowerCandidate,
  WalkinPool,
  LendingType,
  OpeningHours,
  WalkinPeriodIssue,
  WalkinProduct,
  WalkinResource,
} from "../types";

/** One selected product and how many of its units are lent. */
interface Selected {
  product: WalkinProduct;
  quantity: number;
}

/** Units of one product for one period, keyed so stale data is never shown. */
interface Availability {
  key: string;
  resources: WalkinResource[] | null;
  /** Why the pool can't serve the period (closed day, opening hours). */
  issues: WalkinPeriodIssue[];
  error?: string;
}

type Mode = "now" | "later";
type Period = { start: string; end: string };

const inputClass =
  "block w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-sm text-slate-900 dark:text-slate-100 dark:bg-slate-800";

function formatBound(value: string): string {
  // Daily periods are plain dates; hourly ones full datetimes.
  return value.includes("T") ? formatDateTime(value) : formatDate(value);
}

/** Today as a local yyyy-mm-dd string (for the immediate-handout period). */
function todayStr(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Parse a period bound; a date-only end covers the whole day (→ next midnight). */
function toDate(value: string, isEnd: boolean): Date {
  if (value.includes("T")) return new Date(value);
  const [y, m, d] = value.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  if (isEnd) dt.setDate(dt.getDate() + 1);
  return dt;
}

/** Local date (yyyy-mm-dd) + time (hh:mm) as an ISO datetime, or null. */
function localDateTime(date: string, time: string): string | null {
  if (!date || !time) return null;
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const dt = new Date(y, m - 1, d, hh, mm || 0, 0, 0);
  return Number.isNaN(dt.getTime()) ? null : dt.toISOString();
}

const WEEKDAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

/** The opening ranges of a pool on a local yyyy-mm-dd date ([] if closed). */
function openingRanges(hours: OpeningHours | undefined, date: string): [string, string][] {
  if (!hours || !date) return [];
  const [y, m, d] = date.split("-").map(Number);
  return hours[WEEKDAY_KEYS[new Date(y, m - 1, d).getDay()]] ?? [];
}

const pad2 = (n: number) => String(n).padStart(2, "0");
const toMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + (m || 0);
};

/** Full hours ("HH:00") a reservation may start ("start") or end ("end") at on
 *  `date`, inside the pool's opening ranges: a start leaves at least one hour
 *  before the range closes, an end lies at least one hour after it opens. A
 *  pool without any opening hours configured allows every hour. */
function hourOptions(
  hours: OpeningHours | undefined,
  date: string,
  kind: "start" | "end",
): string[] {
  const configured = hours && Object.values(hours).some((r) => r.length > 0);
  if (!configured) {
    return Array.from({ length: 24 }, (_, i) => `${pad2(kind === "start" ? i : i + 1)}:00`)
      .filter((v) => v !== "24:00");
  }
  const out = new Set<number>();
  for (const [open, close] of openingRanges(hours, date)) {
    const first = Math.ceil(toMinutes(open) / 60);
    const last = Math.floor(toMinutes(close) / 60);
    for (let h = first; h <= last; h++) {
      if (kind === "start" ? h < last : h > first) out.add(h);
    }
  }
  return [...out].sort((a, b) => a - b).map((h) => `${pad2(h)}:00`);
}

/** `d` floored to the full hour (start of an hourly hand-out). */
function floorToHour(d: Date): Date {
  const x = new Date(d);
  x.setMinutes(0, 0, 0);
  return x;
}

/** Fallback length of an hourly hand-out when no selected product has a max. */
const DEFAULT_HANDOUT_HOURS = 2;

/** Return hours for an hourly hand-out on `day`: within the opening hours
 *  and, today, after the current full hour. */
function returnHourOptions(hours: OpeningHours | undefined, day: string, today: string): string[] {
  const now = `${pad2(floorToHour(new Date()).getHours())}:00`;
  return hourOptions(hours, day, "end").filter((h) => day !== today || h > now);
}

/** Default return time of an hourly hand-out on `date`: the current full hour
 *  plus `hours`, moved onto the nearest offered hour at or before it (else the
 *  first offered hour). Empty when the day offers none. */
function defaultReturnTime(options: string[], hours: number): string {
  if (options.length === 0) return "";
  const target = `${pad2(Math.min(23, floorToHour(new Date()).getHours() + hours))}:00`;
  const atOrBefore = options.filter((h) => h <= target);
  return atOrBefore.length ? atOrBefore[atOrBefore.length - 1] : options[0];
}

/** Delay before the availability check runs after an edit. */
const CHECK_DEBOUNCE_MS = 300;

/** Local wall-clock time of `d` as a timezone-free millisecond count. */
function wallClock(d: Date): number {
  return Date.UTC(
    d.getFullYear(), d.getMonth(), d.getDate(),
    d.getHours(), d.getMinutes(), d.getSeconds(), d.getMilliseconds(),
  );
}

/** The hourly hand-out period: from the current full hour until `end` (ISO). */
function hourlyHandoutPeriod(end: string): Period | null {
  const start = floorToHour(new Date()).toISOString();
  return end > start ? { start, end } : null;
}

/** Length of a period in the product's unit, counted like the backend:
 *  days = calendar days touched (start day inclusive), hours = started
 *  local wall-clock hours (so a DST day counts the slots, not elapsed time). */
function periodLength(start: string, end: string, unit: LendingType): number {
  const s = toDate(start, false);
  const e = toDate(end, true);
  if (unit === "hours") {
    return Math.max(1, Math.ceil((wallClock(e) - wallClock(s)) / 3_600_000));
  }
  const last = new Date(e.getTime() - 1);
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((day(last) - day(s)) / 86_400_000) + 1;
}

/** Whether `length` lies outside [min, max] (null = open side). */
function outsideLimits(length: number, min: number | null, max: number | null): boolean {
  const lo = limitValue(min);
  const hi = limitValue(max);
  return (lo !== null && length < lo) || (hi !== null && length > hi);
}

/** Default hand-out length: the smallest effective max among the hourly
 *  products, else DEFAULT_HANDOUT_HOURS. */
function defaultHandoutHours(selection: Selected[]): number {
  const maxes = selection
    .filter((s) => s.product.lending_type === "hours")
    .map((s) => limitValue(s.product.effective_max_duration))
    .filter((v): v is number => v !== null);
  return maxes.length ? Math.min(...maxes) : DEFAULT_HANDOUT_HOURS;
}

/** The units handed out for `quantity` slots: a lender's still-free manual
 *  pick per slot wins, the remaining slots take the first free units. Returns
 *  null for a slot nothing is left for. */
function assignUnits(
  resources: WalkinResource[],
  quantity: number,
  picks: (number | null)[],
): (WalkinResource | null)[] {
  const free = resources.filter((r) => !r.conflict);
  const used = new Set<number>();
  const slots: (WalkinResource | null)[] = Array(quantity).fill(null);
  for (let i = 0; i < quantity; i++) {
    const pick = free.find((r) => r.id === picks[i]);
    if (pick && !used.has(pick.id)) {
      slots[i] = pick;
      used.add(pick.id);
    }
  }
  for (let i = 0; i < quantity; i++) {
    if (slots[i]) continue;
    const next = free.find((r) => !used.has(r.id));
    if (next) {
      slots[i] = next;
      used.add(next.id);
    }
  }
  return slots;
}

export function WalkInLendingPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const confirm = useConfirm();
  const context = useFetch<{ pools: WalkinPool[] }>(
    () => api.getWalkinContext(),
    [],
  );

  const [poolId, setPoolId] = useState<number | null>(null);
  const [borrowerQuery, setBorrowerQuery] = useState("");
  const [results, setResults] = useState<BorrowerCandidate[]>([]);
  const [borrower, setBorrower] = useState<BorrowerCandidate | null>(null);
  const [productQuery, setProductQuery] = useState("");
  const [selection, setSelection] = useState<Selected[]>([]);
  // The selection lives only in this page's state; a pool-scope switch
  // remounts the page, so lock the switch while it holds items.
  const hasItems = selection.length > 0;
  useEffect(() => {
    setPoolScopeLocked(hasItems);
    return () => setPoolScopeLocked(false);
  }, [hasItems]);
  // "now" hands out on the spot, "later" creates a confirmed booking.
  const [mode, setMode] = useState<Mode>("now");
  const handOut = mode === "now";
  // One period for all items. "now": daily products run from today until the
  // return date, hourly ones from the current full hour for n hours.
  const [returnDate, setReturnDate] = useState("");
  // Hourly hand-outs: the return time ("HH:00") on the return date.
  const [returnTime, setReturnTime] = useState("");
  // "later": whole days from → until (daily); the times apply to hourly ones.
  const [fromDate, setFromDate] = useState("");
  const [untilDate, setUntilDate] = useState("");
  const [fromTime, setFromTime] = useState("");
  const [untilTime, setUntilTime] = useState("");
  // Units per product for the current period, and the lender's manual picks.
  const [availability, setAvailability] = useState<Record<number, Availability>>({});
  const [picks, setPicks] = useState<Record<number, (number | null)[]>>({});
  const [changing, setChanging] = useState<Record<number, boolean>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const pools = context.data?.pools ?? [];
  useEffect(() => {
    if (poolId === null && pools.length) setPoolId(pools[0].id);
  }, [pools, poolId]);
  const noteRequired = !!pools.find((p) => p.id === poolId)?.require_booking_note;
  const noteMissing = noteRequired && note.trim() === "";

  const productsFetch = useFetch<{ products: WalkinProduct[] }>(
    () =>
      poolId
        ? api.getWalkinProducts(poolId)
        : Promise.resolve({ products: [] }),
    [poolId],
  );
  const products = productsFetch.data?.products ?? [];

  const hasDaily = selection.some((s) => s.product.lending_type === "days");
  const hasHourly = selection.some((s) => s.product.lending_type === "hours");

  // Hourly hand-outs re-take "now" on every render (and again on submit), so
  // a page left open past the hour doesn't hand out from a stale start.
  const today = todayStr();
  const poolHours = pools.find((p) => p.id === poolId)?.opening_hours;
  // Return hours offered for an hourly hand-out: within the opening hours of
  // the return day and, today, after the current full hour.
  const returnTimeOptions = returnHourOptions(poolHours, returnDate, today);
  const handoutEnd = localDateTime(returnDate, returnTime);
  const laterHourlyStart = localDateTime(fromDate, fromTime);
  const laterHourlyEnd = localDateTime(untilDate, untilTime);
  // A reservation can't start before the current full hour (today's past
  // hours are gone); ISO strings from toISOString compare chronologically.
  const startInPast =
    !!laterHourlyStart && laterHourlyStart < floorToHour(new Date()).toISOString();

  /** The period of a product of `type` under the current inputs, or null. */
  function periodFor(type: LendingType): Period | null {
    if (handOut) {
      if (type === "hours") {
        return returnDate >= today && handoutEnd ? hourlyHandoutPeriod(handoutEnd) : null;
      }
      return returnDate && returnDate >= today ? { start: today, end: returnDate } : null;
    }
    if (!fromDate || !untilDate || untilDate < fromDate || fromDate < today) return null;
    if (type === "days") return { start: fromDate, end: untilDate };
    return laterHourlyStart && laterHourlyEnd && laterHourlyEnd > laterHourlyStart && !startInPast
      ? { start: laterHourlyStart, end: laterHourlyEnd }
      : null;
  }
  const dailyPeriod = periodFor("days");
  const hourlyPeriod = periodFor("hours");
  const periodComplete =
    (!hasDaily || dailyPeriod !== null) && (!hasHourly || hourlyPeriod !== null);
  // Why the period isn't usable yet, shown instead of a silently disabled
  // button (null = complete, or nothing selected yet).
  const periodHint: string | null = (() => {
    if (selection.length === 0 || periodComplete) return null;
    if (handOut) {
      if (hasDaily && returnDate && returnDate < today) return t("The return date is in the past.");
      if (hasHourly && returnDate && returnTimeOptions.length === 0) {
        return t("No return time left on this day within the opening hours.");
      }
      return t("Enter the period to check availability.");
    }
    if (fromDate && fromDate < today) return t("The start date is in the past.");
    if (fromDate && untilDate && untilDate < fromDate) return t("The end date is before the start date.");
    if (hasHourly && startInPast) return t("The start time is in the past.");
    // Hourly reservations can only start/end within the pool's opening hours.
    const openingHours = pools.find((p) => p.id === poolId)?.opening_hours;
    if (hasHourly && fromDate && hourOptions(openingHours, fromDate, "start").length === 0) {
      return t("The pool is closed on the start day.");
    }
    if (hasHourly && untilDate && hourOptions(openingHours, untilDate, "end").length === 0) {
      return t("The pool is closed on the end day.");
    }
    if (hasHourly && laterHourlyStart && laterHourlyEnd && laterHourlyEnd <= laterHourlyStart) {
      return t("The end time must be after the start time.");
    }
    return t("Enter the period to check availability.");
  })();
  const periodOf = (p: WalkinProduct) =>
    p.lending_type === "hours" ? hourlyPeriod : dailyPeriod;
  const checkKey = (p: WalkinProduct): string | null => {
    const period = periodOf(p);
    return period && poolId ? `${poolId}|${p.id}|${period.start}|${period.end}` : null;
  };

  // The products whose units must be (re)checked, as one stable string.
  const pendingChecks = selection
    .map((s) => {
      const key = checkKey(s.product);
      return key && availability[s.product.id]?.key !== key ? key : null;
    })
    .filter((k): k is string => k !== null)
    .join(",");

  // The key each selected product currently needs; a response for any other
  // key is stale and dropped. Keys already requested aren't sent again.
  const wantedKeys = useRef<Record<number, string | null>>({});
  wantedKeys.current = Object.fromEntries(
    selection.map((s) => [s.product.id, checkKey(s.product)]),
  );
  const inFlight = useRef<Set<string>>(new Set());

  // Debounced availability check.
  useEffect(() => {
    if (!pendingChecks) return;
    const handle = setTimeout(() => {
      for (const key of pendingChecks.split(",")) {
        if (inFlight.current.has(key)) continue;
        inFlight.current.add(key);
        const [pool, product, start, end] = key.split("|");
        const productId = Number(product);
        const store = (entry: Availability) => {
          inFlight.current.delete(key);
          if (wantedKeys.current[productId] === key) {
            setAvailability((prev) => ({ ...prev, [productId]: entry }));
          }
        };
        api
          .getWalkinResources(Number(pool), productId, start, end)
          .then(({ resources, issues }) => store({ key, resources, issues: issues ?? [] }))
          .catch((err) =>
            store({
              key,
              resources: null,
              issues: [],
              error: err instanceof Error ? err.message : String(err),
            }),
          );
      }
    }, CHECK_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [pendingChecks]);

  // Per-row state derived from the current period and the fetched units.
  const rows = selection.map((s) => {
    const p = s.product;
    const period = periodOf(p);
    const key = checkKey(p);
    const avail = key ? availability[p.id] : undefined;
    const fresh = avail && avail.key === key ? avail : undefined;
    const resources = fresh?.resources ?? null;
    const free = resources ? resources.filter((r) => !r.conflict) : [];
    const slots = resources ? assignUnits(resources, s.quantity, picks[p.id] ?? []) : [];
    const assigned = slots.filter((r): r is WalkinResource => r !== null);
    // A closed pickup/return day or hours outside the opening hours block a
    // reservation; a hand-out only warns (the lender is at the desk), and
    // ignores the pickup day — that is today, at the open desk.
    const issues = fresh?.issues ?? [];
    const blockingIssues = handOut ? [] : issues;
    const warningIssues = handOut ? issues.filter((i) => i !== "pickup_closed") : [];
    const status: "none" | "loading" | "error" | "closed" | "short" | "ok" = !period
      ? "none"
      : !fresh
        ? "loading"
        : fresh.error
          ? "error"
          : blockingIssues.length > 0
            ? "closed"
            : assigned.length < s.quantity
              ? "short"
              : "ok";
    // Limits only warn: the period vs. each handed-out unit's limits.
    const outsideRanges =
      status === "ok" && period
        ? [
            ...new Set(
              assigned
                .filter((r) =>
                  outsideLimits(
                    periodLength(period.start, period.end, p.lending_type),
                    r.effective_min_duration,
                    r.effective_max_duration,
                  ),
                )
                .map((r) =>
                  durationRange(r.effective_min_duration, r.effective_max_duration, p.lending_type),
                ),
            ),
          ]
        : [];
    return {
      ...s, period, status, free, assigned, error: fresh?.error, outsideRanges,
      blockingIssues, warningIssues,
    };
  });

  function issueLabel(issue: WalkinPeriodIssue): string {
    if (issue === "pickup_closed") return t("Pickup on a closed day");
    if (issue === "return_closed") return t("Return on a closed day");
    return t("Outside opening hours");
  }

  // Debounced borrower search.
  useEffect(() => {
    const term = borrowerQuery.trim();
    // The backend requires 3 characters (#160) — don't fire shorter queries.
    if (term.length < 3) {
      setResults([]);
      return;
    }
    const handle = setTimeout(() => {
      api.searchBorrowers(term).then(setResults).catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(handle);
  }, [borrowerQuery]);

  if (user && !user.is_lender && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  function clearSelection() {
    setSelection([]);
    setPicks({});
    setChanging({});
    setAvailability({});
    setProductQuery("");
  }

  // Products belong to the pool, so a pool change starts fresh (asked first
  // when items are listed).
  async function changePool(id: number) {
    if (id === poolId) return;
    if (
      selection.length > 0 &&
      !(await confirm({ message: t("Changing the pool removes the items chosen so far.") }))
    ) {
      return;
    }
    setPoolId(id);
    clearSelection();
    setMessage(null);
  }

  // Switching between immediate hand-out and reservation drops the items and
  // the period, so the two period sources never mix. With items, ask first.
  async function changeMode(next: Mode) {
    if (next === mode) return;
    if (
      selection.length > 0 &&
      !(await confirm({ message: t("Switching mode removes the items chosen so far.") }))
    ) {
      return;
    }
    setMode(next);
    clearSelection();
    setReturnDate("");
    setReturnTime("");
    setFromDate("");
    setUntilDate("");
    setFromTime("");
    setUntilTime("");
    setMessage(null);
  }

  // Reservation times are full hours within the pool's opening hours. When a
  // date changes, a time that isn't offered on the new day moves to the first
  // start / last end hour of that day.
  const startOptions = hourOptions(poolHours, fromDate, "start");
  const endOptions = hourOptions(poolHours, untilDate, "end").filter(
    (h) => fromDate !== untilDate || !fromTime || h > fromTime,
  );
  function prefillTimes(from: string, until: string) {
    const starts = hourOptions(poolHours, from, "start");
    const ends = hourOptions(poolHours, until, "end");
    if (from && !starts.includes(fromTime)) setFromTime(starts[0] ?? "");
    if (until && !ends.includes(untilTime)) setUntilTime(ends[ends.length - 1] ?? "");
  }

  // Hourly hand-out: default the return date to today and the return time to
  // the shortest max of the selected hourly products (else a fallback) after
  // the current full hour — unless the lender has already chosen a time.
  function prefillReturn(next: Selected[], date = returnDate) {
    const day = date || today;
    if (!date) setReturnDate(day);
    if (returnTime) return;
    const options = returnHourOptions(poolHours, day, today);
    setReturnTime(defaultReturnTime(options, defaultHandoutHours(next)));
  }

  // Picking a product adds it, or one more unit of it.
  function pickProduct(p: WalkinProduct) {
    setMessage(null);
    const next = selection.some((s) => s.product.id === p.id)
      ? selection.map((s) => (s.product.id === p.id ? { ...s, quantity: s.quantity + 1 } : s))
      : [...selection, { product: p, quantity: 1 }];
    setSelection(next);
    if (p.lending_type === "hours" && handOut) prefillReturn(next);
    if (p.lending_type === "hours" && !handOut) prefillTimes(fromDate, untilDate);
  }

  function changeQuantity(productId: number, delta: number) {
    const current = selection.find((s) => s.product.id === productId);
    if (current && current.quantity + delta <= 0) {
      // The row goes away: forget its unit picks and open unit selects too.
      setPicks((prev) => ({ ...prev, [productId]: [] }));
      setChanging((prev) => ({ ...prev, [productId]: false }));
    }
    const next = selection
      .map((s) => (s.product.id === productId ? { ...s, quantity: s.quantity + delta } : s))
      .filter((s) => s.quantity > 0);
    setSelection(next);
  }

  function removeProduct(productId: number) {
    const row = selection.find((s) => s.product.id === productId);
    if (row) changeQuantity(productId, -row.quantity);
  }

  function pickUnit(productId: number, slot: number, resourceId: number) {
    setPicks((prev) => {
      const current = [...(prev[productId] ?? [])];
      // Pin the other slots to what they show now, so they don't shuffle.
      const row = rows.find((r) => r.product.id === productId);
      row?.assigned.forEach((r, i) => {
        if (current[i] == null) current[i] = r.id;
      });
      // Swap if another slot holds this unit.
      const other = current.findIndex((id, i) => i !== slot && id === resourceId);
      if (other !== -1) current[other] = current[slot] ?? null;
      current[slot] = resourceId;
      return { ...prev, [productId]: current };
    });
  }

  async function submit() {
    if (!borrower || !poolId || !canSubmit) return;
    setBusy(true);
    setMessage(null);
    try {
      const booking = await api.createWalkin({
        borrower: borrower.id,
        pool: poolId,
        hand_out: handOut,
        note: note.trim(),
        // One entry per handed-out unit; hourly hand-outs run from the
        // current full hour at submit time (periodFor re-takes "now").
        items: rows.flatMap((row) => {
          const period = periodFor(row.product.lending_type)!;
          return row.assigned.map((r) => ({
            product: row.product.id,
            resource: r.id,
            start: period.start,
            end: period.end,
          }));
        }),
      });
      setMessage({
        ok: true,
        text: handOut
          ? t("Created {{code}} — handed out for {{user}}.", {
              code: booking.code,
              user: borrower.username,
            })
          : t("Created {{code}} — reserved for {{user}}.", {
              code: booking.code,
              user: borrower.username,
            }),
      });
      clearSelection();
      setBorrower(null);
      setBorrowerQuery("");
      setNote("");
      setReturnDate("");
      setReturnTime("");
      setFromDate("");
      setUntilDate("");
      setFromTime("");
      setUntilTime("");
    } catch (err) {
      // Includes a 400 `note_required` (the pool's note setting changed
      // meanwhile) and a 409 when a unit was just taken: shown as is, and
      // the availability is checked again.
      setAvailability({});
      setMessage({
        ok: false,
        text: err instanceof Error ? err.message : t("Could not create the lending."),
      });
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = Boolean(
    borrower &&
      poolId &&
      selection.length > 0 &&
      periodComplete &&
      rows.every((r) => r.status === "ok") &&
      !noteMissing &&
      !busy,
  );

  const timeInputs = !handOut && hasHourly;

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs showPoolScope />

      <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Walk-in lending")}</h2>
      <div className="mt-2">
        <SortToggle<Mode>
          value={mode}
          onChange={changeMode}
          label={t("Mode")}
          options={[
            { value: "now", label: t("Hand out now") },
            { value: "later", label: t("Booking for later") },
          ]}
        />
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {handOut
            ? t("Handed out to the person right away; you choose the return date.")
            : t("Creates a confirmed booking for the person; pickup later at the desk.")}
        </p>
        {handOut && rows.some((r) => r.product.self_service) && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {t("On-site items without hand-out are only booked, not handed out.")}
          </p>
        )}
      </div>
      <p className="mb-4 mt-2 text-xs text-slate-600 dark:text-slate-300">
        {t(
          "Lend out on the spot for someone at the desk. Lead time and the booking horizon are skipped; availability is still checked.",
        )}
      </p>

      {context.loading && <Loading />}
      {context.error && <ErrorBox message={context.error} />}

      {context.data && pools.length === 0 && (
        <p className="rounded-lg bg-amber-50 dark:bg-amber-950/40 p-3 text-sm text-amber-800 dark:text-amber-300">
          {t("You don't manage any pool yet.")}
        </p>
      )}

      {context.data && pools.length > 0 && (
        <div className="space-y-5">
          {/* Borrower */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("1. Borrower")}</h3>
            {borrower ? (
              <div className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-800/50 p-3">
                <div className="text-sm">
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    {borrower.username}
                  </span>
                  {borrower.full_name && (
                    <span className="text-slate-600 dark:text-slate-300"> · {borrower.full_name}</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setBorrower(null)}
                  className="text-sm text-slate-600 dark:text-slate-300 hover:underline"
                >
                  {t("Change")}
                </button>
              </div>
            ) : (
              <div className="relative">
                <input
                  value={borrowerQuery}
                  onChange={(e) => setBorrowerQuery(e.target.value)}
                  placeholder={t("Search by name, username or e-mail…")}
                  className={inputClass}
                />
                {results.length > 0 && (
                  <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg">
                    {results.map((candidate) => (
                      <li key={candidate.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setBorrower(candidate);
                            setResults([]);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700"
                        >
                          <span className="font-medium text-slate-900 dark:text-slate-100">
                            {candidate.username}
                          </span>
                          {candidate.full_name && (
                            <span className="text-slate-600 dark:text-slate-300">
                              {" "}
                              · {candidate.full_name}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>

          {/* Pool + products */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("2. Items")}</h3>
            <label className="block text-xs text-slate-600 dark:text-slate-300">
              {t("Pool")}
              <select
                value={poolId ?? ""}
                onChange={(e) => void changePool(Number(e.target.value))}
                className={`mt-1 ${inputClass}`}
              >
                {pools.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.room ? ` · ${p.room}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <div className="mt-3">
              <GroupedProductPicker
                products={products}
                query={productQuery}
                onQueryChange={setProductQuery}
                onPick={pickProduct}
                placeholder={t("Search products in this pool…")}
                renderMeta={(p) => (
                  <>
                    {p.lending_type === "hours" ? t("hourly") : t("daily")}
                    {p.use_type === "onsite" && (
                      <>
                        {" "}
                        <OnsiteTag short />
                      </>
                    )}
                    {(limitValue(p.effective_min_duration) !== null ||
                      limitValue(p.effective_max_duration) !== null) &&
                      ` · ${durationRange(p.effective_min_duration, p.effective_max_duration, p.lending_type)}`}
                  </>
                )}
              />
              {productsFetch.loading && (
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-300">{t("Loading…")}</p>
              )}
            </div>

            {rows.length > 0 && (
              <ul className="mt-3 space-y-2">
                {rows.map((row) => {
                  const p = row.product;
                  return (
                    <li
                      key={p.id}
                      className="rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2 text-sm"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span>
                          <span className="font-medium text-slate-900 dark:text-slate-100">{p.title}</span>
                          <span className="text-slate-600 dark:text-slate-300">
                            {" · "}
                            {p.lending_type === "hours" ? t("hourly") : t("daily")}
                          </span>
                          {p.use_type === "onsite" && (
                            <>
                              {" "}
                              <OnsiteTag short />
                            </>
                          )}
                        </span>
                        <span className="flex items-center gap-3">
                          <span
                            className="inline-flex items-center rounded-full border border-slate-300 dark:border-slate-600"
                            role="group"
                            aria-label={t("Quantity of {{product}}", { product: p.title })}
                          >
                            <button
                              type="button"
                              onClick={() => changeQuantity(p.id, -1)}
                              aria-label={t("Decrease quantity of {{product}}", { product: p.title })}
                              className="rounded-l-full p-1.5 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                            >
                              <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                            <span className="min-w-[2ch] text-center tabular-nums text-slate-900 dark:text-slate-100">
                              {row.quantity}
                            </span>
                            <button
                              type="button"
                              onClick={() => changeQuantity(p.id, 1)}
                              aria-label={t("Increase quantity of {{product}}", { product: p.title })}
                              className="rounded-r-full p-1.5 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                            >
                              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </span>
                          <button
                            type="button"
                            onClick={() => removeProduct(p.id)}
                            aria-label={t("Remove {{product}}", { product: p.title })}
                            className="text-red-600 dark:text-red-300 hover:underline"
                          >
                            {t("Remove")}
                          </button>
                        </span>
                      </div>

                      {/* Availability in the chosen period (announced politely). */}
                      <div role="status" aria-live="polite" className="mt-1 text-xs">
                        {/* Names the row (and its quantity) for screen readers. */}
                        <span className="sr-only">
                          {t("{{product}}, quantity {{quantity}}:", {
                            product: p.title,
                            quantity: row.quantity,
                          })}{" "}
                        </span>
                        {row.status === "loading" && (
                          <span className="text-slate-500 dark:text-slate-400">{t("Checking availability…")}</span>
                        )}
                        {row.status === "error" && (
                          <span className="text-red-600 dark:text-red-300">{row.error}</span>
                        )}
                        {row.status === "short" && (
                          <span className="text-red-600 dark:text-red-300">
                            {row.free.length === 0
                              ? t("Not available in this period")
                              : t("Only {{free}} of {{wanted}} available", {
                                  free: row.free.length,
                                  wanted: row.quantity,
                                })}
                          </span>
                        )}
                        {row.status === "closed" && (
                          <span className="block text-red-600 dark:text-red-300">
                            {row.blockingIssues.map((i) => issueLabel(i)).join(" · ")}
                          </span>
                        )}
                        {row.status === "ok" && (
                          <span className="inline-flex items-center gap-1 text-green-700 dark:text-green-300">
                            <Check className="h-3.5 w-3.5" aria-hidden="true" />
                            {row.assigned.map((r) => r.inventory_number).join(", ")}
                          </span>
                        )}
                        {row.status !== "closed" &&
                          row.warningIssues.map((i) => (
                            <span
                              key={i}
                              className="mt-1 block w-fit rounded-md bg-amber-50 px-2 py-0.5 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                            >
                              {issueLabel(i)}
                            </span>
                          ))}
                        {row.outsideRanges.map((range) => (
                          <span
                            key={range}
                            className="mt-1 block w-fit rounded-md bg-amber-50 px-2 py-0.5 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                          >
                            {t("Outside the lending-duration limit ({{range}}).", { range })}
                          </span>
                        ))}
                      </div>

                      {row.status === "ok" && row.free.length > row.quantity && (
                        <button
                          type="button"
                          onClick={() => setChanging((prev) => ({ ...prev, [p.id]: !prev[p.id] }))}
                          aria-expanded={!!changing[p.id]}
                          className="mt-1 text-xs text-slate-600 dark:text-slate-300 underline-offset-2 hover:underline"
                        >
                          {t("Choose another item")}
                        </button>
                      )}

                      {row.status === "ok" && row.free.length > row.quantity && changing[p.id] && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {row.assigned.map((unit, slot) => (
                            <label key={slot} className="text-xs text-slate-600 dark:text-slate-300">
                              {t("Item {{n}}", { n: slot + 1 })}
                              <select
                                value={unit.id}
                                onChange={(e) => pickUnit(p.id, slot, Number(e.target.value))}
                                className={`mt-1 ${inputClass}`}
                              >
                                {row.free.map((r) => (
                                  <option key={r.id} value={r.id}>
                                    {r.inventory_number}
                                  </option>
                                ))}
                              </select>
                            </label>
                          ))}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* One period for all items */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("3. Period")}</h3>
            {selection.length === 0 ? (
              <p className="text-xs text-slate-600 dark:text-slate-300">{t("Choose items first.")}</p>
            ) : handOut ? (
              <div className="flex flex-wrap gap-4">
                {(hasDaily || hasHourly) && (
                  <label className="block text-xs text-slate-600 dark:text-slate-300">
                    {t("Return date")}
                    <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                    <input
                      type="date"
                      required
                      min={today}
                      value={returnDate}
                      onChange={(e) => {
                        const day = e.target.value;
                        setReturnDate(day);
                        // Keep the return time if the new day still offers it.
                        if (hasHourly) {
                          const options = returnHourOptions(poolHours, day, today);
                          if (!options.includes(returnTime)) {
                            setReturnTime(defaultReturnTime(options, defaultHandoutHours(selection)));
                          }
                        }
                      }}
                      className={`mt-1 sm:w-52 ${inputClass}`}
                    />
                    {hasDaily && (
                      <span className="mt-1 block text-slate-500 dark:text-slate-400">
                        {t("Handed out today, due back on this date.")}
                      </span>
                    )}
                  </label>
                )}
                {hasHourly && (
                  <label className="block text-xs text-slate-600 dark:text-slate-300">
                    {t("Return time")}
                    <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                    <select
                      required
                      value={returnTimeOptions.includes(returnTime) ? returnTime : ""}
                      onChange={(e) => setReturnTime(e.target.value)}
                      disabled={!returnDate || returnTimeOptions.length === 0}
                      className={`mt-1 sm:w-32 ${inputClass}`}
                    >
                      <option value="">–</option>
                      {returnTimeOptions.map((h) => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                    {hourlyPeriod && (
                      <span className="mt-1 block text-slate-500 dark:text-slate-400">
                        {t("Handed out from {{start}}, due back at {{end}}.", {
                          start: formatBound(hourlyPeriod.start),
                          end: formatBound(hourlyPeriod.end),
                        })}
                      </span>
                    )}
                  </label>
                )}
              </div>
            ) : (
              <div className="flex flex-wrap gap-4">
                <label className="block text-xs text-slate-600 dark:text-slate-300">
                  {t("From")}
                  <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                  <input
                    type="date"
                    required
                    min={today}
                    value={fromDate}
                    onChange={(e) => {
                      setFromDate(e.target.value);
                      prefillTimes(e.target.value, untilDate);
                    }}
                    className={`mt-1 sm:w-44 ${inputClass}`}
                  />
                </label>
                {timeInputs && (
                  <label className="block text-xs text-slate-600 dark:text-slate-300">
                    {t("Start time")}
                    <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                    <select
                      required
                      value={fromTime}
                      onChange={(e) => {
                        const next = e.target.value;
                        setFromTime(next);
                        // Same day: keep the end after the new start.
                        if (fromDate === untilDate && untilTime && next && untilTime <= next) {
                          const later = hourOptions(poolHours, untilDate, "end").find((h) => h > next);
                          setUntilTime(later ?? "");
                        }
                      }}
                      disabled={!fromDate || startOptions.length === 0}
                      className={`mt-1 sm:w-32 ${inputClass}`}
                    >
                      <option value="">–</option>
                      {startOptions.map((h) => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="block text-xs text-slate-600 dark:text-slate-300">
                  {t("Until")}
                  <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                  <input
                    type="date"
                    required
                    min={fromDate || undefined}
                    value={untilDate}
                    onChange={(e) => {
                      setUntilDate(e.target.value);
                      prefillTimes(fromDate, e.target.value);
                    }}
                    className={`mt-1 sm:w-44 ${inputClass}`}
                  />
                </label>
                {timeInputs && (
                  <label className="block text-xs text-slate-600 dark:text-slate-300">
                    {t("End time")}
                    <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                    <select
                      required
                      value={untilTime}
                      onChange={(e) => setUntilTime(e.target.value)}
                      disabled={!untilDate || endOptions.length === 0}
                      className={`mt-1 sm:w-32 ${inputClass}`}
                    >
                      <option value="">–</option>
                      {endOptions.map((h) => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                )}
                {timeInputs && (
                  <p className="basis-full text-xs text-slate-500 dark:text-slate-400">
                    {t("The times apply to hourly items; daily items use whole days.")}
                  </p>
                )}
              </div>
            )}
            {periodHint && (
              <p
                role="status"
                className={`mt-2 text-xs ${
                  periodHint === t("Enter the period to check availability.")
                    ? "text-slate-500 dark:text-slate-400"
                    : "text-amber-700 dark:text-amber-300"
                }`}
              >
                {periodHint}
              </p>
            )}
          </section>

          {/* Confirm */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("4. Confirm")}</h3>
            <label className="mb-3 block text-xs text-slate-600 dark:text-slate-300">
              {noteRequired ? (
                <>
                  {t("Note")}
                  <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                </>
              ) : (
                t("Note (optional)")
              )}
              <textarea
                rows={2}
                required={noteRequired}
                aria-invalid={noteMissing || undefined}
                aria-describedby={noteMissing ? "walkin-note-hint" : undefined}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("e.g. reason for the lending, agreed return, …")}
                className={`mt-1 ${inputClass}`}
              />
              {noteMissing && (
                <span id="walkin-note-hint" className="mt-1 block text-amber-700 dark:text-amber-300">
                  {t("This pool requires a note.")}
                </span>
              )}
            </label>

            <div className="mt-3">
              <button
                type="button"
                onClick={() => void submit()}
                disabled={!canSubmit}
                className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
              >
                {busy ? t("Saving…") : handOut ? t("Hand out") : t("Create booking")}
              </button>
              {message && (
                <p
                  role="status"
                  className={`mt-2 text-sm ${
                    message.ok ? "text-green-700 dark:text-green-300" : "text-red-600 dark:text-red-300"
                  }`}
                >
                  {message.text}
                  {message.ok && (
                    <>
                      {" "}
                      <Link
                        to="/manage/list"
                        className="font-medium underline underline-offset-2"
                      >
                        {t("View bookings")}
                      </Link>
                    </>
                  )}
                </p>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
