// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "./Toast";
import i18n from "../i18n";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { useCart } from "../cart";
import { useFetch } from "../useFetch";
import { MonthCalendar } from "./MonthCalendar";
import type { HourlyAvailability, HourlyCalendarDay } from "../types";

const pad = (n: number) => String(n).padStart(2, "0");
const isoOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
const todayIso = () => new Date().toLocaleDateString("en-CA");

interface HourlyBookingCalendarProps {
  /** Product to book; omit when supplying custom data-source props (e.g. sets). */
  productId?: number;
  /** Override the per-day utilization source (defaults to the product endpoint). */
  fetchCalendar?: (from: string, to: string) => Promise<{ days: HourlyCalendarDay[] }>;
  /** Override the per-day hour-slot source (defaults to the product endpoint). */
  fetchDay?: (date: string) => Promise<HourlyAvailability>;
  /** Override the add-to-cart action (defaults to cart.add for the product). */
  onAdd?: (start: string, end: string) => Promise<void>;
  /** Extra cache key so callers can force a reload (e.g. a shared cart version). */
  reloadKey?: string | number;
  /** Label of the confirm button (default "Add to cart"). */
  addLabel?: string;
  /** Success message after adding (default "Added to your cart."). */
  addedText?: string;
  /** Show the "Go to cart" link in the success message (default true). */
  showCartLink?: boolean;
  /** Pool the borrower chose (#10); scopes availability and the add-to-cart
   *  call to that pool instead of every eligible one. */
  pool?: number;
}

export function HourlyBookingCalendar({
  productId,
  fetchCalendar,
  fetchDay,
  onAdd,
  reloadKey,
  addLabel = i18n.t("Add to cart"),
  addedText = i18n.t("Added to your cart."),
  showCartLink = true,
  pool,
}: HourlyBookingCalendarProps) {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const { add } = useCart();
  const toast = useToast();
  const fetchCal =
    fetchCalendar ??
    ((from: string, to: string) => api.getHourlyCalendar(productId!, from, to, pool));
  const fetchHours =
    fetchDay ?? ((d: string) => api.getHourlyAvailability(productId!, d, pool));
  const addFn = onAdd ?? ((s: string, e: string) => add(productId!, s, e, pool));
  const sourceKey = reloadKey ?? `p${productId}-${pool ?? "any"}`;
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [date, setDate] = useState<string | null>(null);
  // Selected slot index range [startIdx, endIdx] (inclusive); endIdx null = picking.
  const [startIdx, setStartIdx] = useState<number | null>(null);
  const [endIdx, setEndIdx] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  // A failed add stays visible (the page can't continue) — not a toast.
  const [error, setError] = useState<{ text: string; relogin: boolean } | null>(null);

  const today = todayIso();
  const from = isoOf(view.year, view.month, 1);
  const to = isoOf(view.month === 11 ? view.year + 1 : view.year, (view.month + 1) % 12, 1);

  const calendar = useFetch<{ days: HourlyCalendarDay[] }>(
    () => fetchCal(from, to),
    [sourceKey, from, to, version],
  );
  const byDate = useMemo(() => {
    const map: Record<string, HourlyCalendarDay> = {};
    calendar.data?.days.forEach((d) => (map[d.date] = d));
    return map;
  }, [calendar.data]);

  const hourly = useFetch<HourlyAvailability | null>(
    () => (date ? fetchHours(date) : Promise.resolve(null)),
    [sourceKey, date, version],
  );
  const slots = hourly.data?.slots ?? [];

  function pickDay(iso: string) {
    setDate(iso);
    setStartIdx(null);
    setEndIdx(null);
  }

  function pickSlot(i: number) {
    if (startIdx === null || endIdx !== null) {
      setStartIdx(i);
      setEndIdx(null);
    } else if (i >= startIdx) {
      setEndIdx(i);
    } else {
      setStartIdx(i);
    }
  }

  // Drag-to-select across the hour grid.
  const anchor = useRef<number | null>(null);
  const dragMoved = useRef(false);

  useEffect(() => {
    function onUp() {
      anchor.current = null;
    }
    window.addEventListener("pointerup", onUp);
    return () => window.removeEventListener("pointerup", onUp);
  }, []);

  function onSlotPointerDown(i: number) {
    anchor.current = i;
    dragMoved.current = false;
  }

  function onSlotPointerEnter(i: number) {
    if (anchor.current === null) return;
    dragMoved.current = true;
    const a = Math.min(anchor.current, i);
    const b = Math.max(anchor.current, i);
    setStartIdx(a);
    setEndIdx(b === a ? null : b);
  }

  function onSlotPointerUp(i: number) {
    if (anchor.current === null) return;
    if (dragMoved.current) {
      const a = Math.min(anchor.current, i);
      const b = Math.max(anchor.current, i);
      setStartIdx(a);
      setEndIdx(b === a ? null : b);
    } else {
      pickSlot(i);
    }
    anchor.current = null;
  }

  const lo = startIdx;
  const hi = endIdx ?? startIdx;
  const selected = lo !== null && hi !== null ? slots.slice(lo, hi + 1) : [];
  const hours = selected.length;
  const minH = hourly.data?.min_hours ?? 1;
  const maxH = hourly.data?.max_hours ?? null;
  const allFree = selected.every((s) => s.available > 0);
  const contiguous = selected.every((s, i) => i === 0 || selected[i - 1].end === s.start);
  const withinMin = hours >= (minH ?? 1);
  const withinMax = maxH === null || hours <= maxH;
  const valid = hours > 0 && allFree && contiguous && withinMin && withinMax;

  async function addToCart() {
    if (!valid || lo === null || hi === null) return;
    setBusy(true);
    setError(null);
    try {
      await addFn(slots[lo].start, slots[hi].end);
      // Clear the selection (disabling the button) so the same period isn't
      // added twice by accident; the toast + header cart badge confirm the add.
      setStartIdx(null);
      setEndIdx(null);
      setVersion((v) => v + 1);
      toast.success(
        addedText,
        showCartLink ? { to: "/cart", actionLabel: t("Go to cart") } : undefined,
      );
    } catch (err) {
      const notAuth = err instanceof ApiError && (err.status === 401 || err.status === 403);
      setError({
        relogin: notAuth,
        text: notAuth
          ? t("Your session has expired — please sign in again.")
          : err instanceof Error
            ? err.message
            : t("Could not add to cart."),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Availability & booking")}</h2>

      <MonthCalendar
        year={view.year}
        month={view.month}
        onMonthChange={(year, month) => setView({ year, month })}
        onDayClick={pickDay}
        isSelected={(iso) => iso === date}
        isClosed={(iso) => byDate[iso]?.closed ?? false}
        isDisabled={(iso) => iso < today}
        dayLabel={(iso, label) => {
          const d = byDate[iso];
          if (!d || d.closed) return `${label}, ${t("closed")}`;
          if (d.booked_pct === null) return label;
          return `${label}, ${t("{{pct}}% of the day booked", { pct: d.booked_pct })}`;
        }}
        renderDay={(iso) => {
          const d = byDate[iso];
          if (!d || d.closed || d.booked_pct === null) return null;
          const pct = d.booked_pct;
          const cls =
            pct >= 100
              ? "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300"
              : pct >= 50
                ? "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
                : "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300";
          return (
            <span
              className={`mt-1 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-bold ${cls}`}
              title={t("{{pct}}% of the day booked", { pct })}
            >
              {pct}%
            </span>
          );
        }}
      />

      <p className="mt-3 text-xs text-slate-600 dark:text-slate-300">
        {t("The percentage shows how much of each day is already booked (")}
        <span className="font-semibold text-amber-600 dark:text-amber-400">{t("orange")}</span>
        {t(" from 50%, ")}
        <span className="font-semibold text-red-600 dark:text-red-400">{t("red")}</span>
        {t(
          " when full). Greyed days are closed. Pick a day, then click the start and end hour — or drag across the hours.",
        )}
      </p>

      {date && (
        <div className="mt-4">
          <h3 className="mb-2 text-sm font-medium text-slate-900 dark:text-slate-100">{t("Hours on {{date}}", { date })}</h3>
          {hourly.loading && <p className="text-sm text-slate-600 dark:text-slate-300">{t("Loading…")}</p>}
          {!hourly.loading && slots.length === 0 && (
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("Closed on this day.")}</p>
          )}
          <div className="flex select-none flex-wrap gap-1.5">
            {slots.map((slot, i) => {
              const inRange = lo !== null && hi !== null && i >= lo && i <= hi;
              const free = slot.available > 0;
              return (
                <button
                  key={slot.start}
                  type="button"
                  disabled={!free}
                  onPointerDown={() => onSlotPointerDown(i)}
                  onPointerEnter={() => onSlotPointerEnter(i)}
                  onPointerUp={() => onSlotPointerUp(i)}
                  title={t("{{available}} of {{total}} free", { available: slot.available, total: slot.total })}
                  className={`rounded-lg border px-2.5 py-1 text-xs transition-colors ${
                    inRange
                      ? "border-brand-500 bg-brand-100 text-slate-900"
                      : free
                        ? "border-slate-200 text-slate-700 hover:border-brand-400 dark:border-slate-700 dark:text-slate-200"
                        : "cursor-not-allowed border-slate-100 text-slate-300 dark:border-slate-800 dark:text-slate-300"
                  }`}
                >
                  {slot.label}
                  <span
                    className={`ml-1.5 inline-flex items-center rounded-full px-1.5 py-0.5 text-[11px] font-bold ${
                      free ? "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300" : "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300"
                    }`}
                  >
                    {slot.available}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="mt-4">
            <p className="text-sm text-slate-700 dark:text-slate-200">
              {hours > 0 ? (
                <>
                  {t("Selected:")} <span className="font-medium">{slots[lo!].label}</span> –{" "}
                  <span className="font-medium">{slots[hi!].end.slice(11, 16)}</span> ({hours}h)
                </>
              ) : (
                t("Pick a start and end hour.")
              )}
            </p>
            {hours > 0 && !withinMin && (
              <p className="text-xs text-red-600 dark:text-red-400">{t("Minimum booking is {{n}}h.", { n: minH })}</p>
            )}
            {hours > 0 && !withinMax && (
              <p className="text-xs text-red-600 dark:text-red-400">{t("Maximum booking is {{n}}h.", { n: maxH })}</p>
            )}
            {hours > 0 && (!allFree || !contiguous) && (
              <p className="text-xs text-red-600 dark:text-red-400">
                {t("The selected hours aren’t all available.")}
              </p>
            )}

            <div className="mt-2">
              {user?.authenticated ? (
                <button
                  type="button"
                  onClick={addToCart}
                  disabled={!valid || busy}
                  className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
                >
                  {busy ? t("Adding…") : addLabel}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={login}
                  className="text-sm font-medium text-slate-700 underline underline-offset-2 dark:text-slate-200"
                >
                  {t("Sign in to add to cart")}
                </button>
              )}
            </div>

            {error && (
              <div
                role="alert"
                className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300"
              >
                <p>{error.text}</p>
                {error.relogin && (
                  <button
                    type="button"
                    onClick={login}
                    className="mt-2 rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
                  >
                    {t("Sign in")}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
