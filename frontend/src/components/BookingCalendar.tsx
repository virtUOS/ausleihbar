// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Info, Lock } from "lucide-react";
import i18n from "../i18n";
import { formatDate } from "../dates";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { useCart } from "../cart";
import { useToast } from "./Toast";
import { useFetch } from "../useFetch";
import { MonthCalendar } from "./MonthCalendar";
import type { DayAvailability } from "../types";

const pad = (n: number) => String(n).padStart(2, "0");
const isoOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
const todayIso = () => new Date().toLocaleDateString("en-CA");
const order = (a: string, b: string): [string, string] => (a <= b ? [a, b] : [b, a]);
/** ISO date `n` days after `iso`. */
const addDays = (iso: string, n: number): string => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return d.toLocaleDateString("en-CA");
};

interface BookingCalendarProps {
  /** Product to book; omit when supplying custom data-source props (e.g. sets). */
  productId?: number;
  /** Override the per-day availability source (defaults to the product endpoint). */
  fetchCalendar?: (from: string, to: string) => Promise<{ days: DayAvailability[] }>;
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
  /** Maximum lending duration in days (inclusive span). Caps the selectable
   *  range so a booking can't exceed the product's limit (#47). */
  maxDuration?: number | null;
}

export function BookingCalendar({
  productId,
  fetchCalendar,
  onAdd,
  reloadKey,
  addLabel = i18n.t("Add to cart"),
  addedText = i18n.t("Added to your cart."),
  showCartLink = true,
  maxDuration = null,
}: BookingCalendarProps) {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const { add } = useCart();
  const toast = useToast();
  const fetchCal =
    fetchCalendar ?? ((from: string, to: string) => api.getAvailabilityCalendar(productId!, from, to));
  const addFn = onAdd ?? ((s: string, e: string) => add(productId!, s, e));
  const sourceKey = reloadKey ?? `p${productId}`;
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [reserving, setReserving] = useState(false);
  // A failed add stays visible (the page can't continue) — not a toast.
  const [error, setError] = useState<{ text: string; relogin: boolean } | null>(null);

  // Drag-to-select state (refs so rapid pointer events don't go stale).
  const anchor = useRef<string | null>(null);
  const dragMoved = useRef(false);

  const from = isoOf(view.year, view.month, 1);
  const to = isoOf(view.month === 11 ? view.year + 1 : view.year, (view.month + 1) % 12, 1);

  const { data } = useFetch<{ days: DayAvailability[] }>(
    () => fetchCal(from, to),
    [sourceKey, from, to, version],
  );

  const byDate = useMemo(() => {
    const map: Record<string, DayAvailability> = {};
    data?.days.forEach((d) => (map[d.date] = d));
    return map;
  }, [data]);

  const today = todayIso();

  // Last day still allowed as the end, given the picked start and the product's
  // max duration (a span of `maxDuration` days, start day inclusive).
  const maxEnd = start && maxDuration ? addDays(start, maxDuration - 1) : null;
  // Cap a candidate end day to `from`'s max span (used during click & drag).
  const capEnd = (from: string, candidate: string) =>
    maxDuration ? order(candidate, addDays(from, maxDuration - 1))[0] : candidate;

  // If the pointer is released outside the grid, end the drag (keep the preview).
  useEffect(() => {
    function onUp() {
      if (anchor.current !== null) anchor.current = null;
    }
    window.addEventListener("pointerup", onUp);
    return () => window.removeEventListener("pointerup", onUp);
  }, []);

  function clickSelect(iso: string) {
    if (start && !end && iso >= start) setEnd(capEnd(start, iso));
    else {
      setStart(iso);
      setEnd(null);
    }
  }

  function onPointerDown(iso: string) {
    anchor.current = iso;
    dragMoved.current = false;
  }

  function onPointerEnter(iso: string) {
    if (anchor.current === null) return;
    dragMoved.current = true;
    const [lo, hi] = order(anchor.current, iso);
    setStart(lo);
    setEnd(lo === hi ? null : capEnd(lo, hi));
  }

  function onPointerUp(iso: string) {
    if (anchor.current === null) return;
    if (dragMoved.current) {
      const [lo, hi] = order(anchor.current, iso);
      setStart(lo);
      setEnd(lo === hi ? null : capEnd(lo, hi));
    } else {
      clickSelect(iso);
    }
    anchor.current = null;
  }

  function isSelected(iso: string) {
    if (!start) return false;
    if (!end) return iso === start;
    return iso >= start && iso <= end;
  }

  function isClosed(iso: string) {
    return byDate[iso]?.closed ?? false;
  }

  function isDisabled(iso: string) {
    if (iso < today) return true;
    const a = byDate[iso];
    return !a || a.available === 0;
  }

  // Days beyond the max span are shown greyed ("out of range") but stay
  // interactive: the drag reads their pointer events (so the marking follows
  // the cursor and the highlight caps at the max) and a click there just starts
  // a fresh selection (#47).
  function isMuted(iso: string) {
    return !!(maxEnd && start && iso > maxEnd);
  }

  async function addToCart() {
    if (!start) return;
    setReserving(true);
    setError(null);
    try {
      await addFn(start, end ?? start);
      // Clear the selection (disabling the button) so the same period isn't
      // added twice by accident; the toast + header cart badge confirm the add.
      setStart(null);
      setEnd(null);
      setVersion((v) => v + 1);
      toast.success(
        addedText,
        showCartLink ? { to: "/cart", actionLabel: t("Go to cart") } : undefined,
      );
    } catch (err) {
      // A lost session (401/403) is the common production cause — say so
      // clearly and offer a sign-in, rather than the raw API message.
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
      setReserving(false);
    }
  }

  return (
    <section className="mt-5 rounded-2xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Availability & booking")}</h2>

      <MonthCalendar
        year={view.year}
        month={view.month}
        onMonthChange={(year, month) => setView({ year, month })}
        onDayPointerDown={onPointerDown}
        onDayPointerEnter={onPointerEnter}
        onDayPointerUp={onPointerUp}
        isSelected={isSelected}
        isDisabled={isDisabled}
        isMuted={isMuted}
        isClosed={isClosed}
        dayLabel={(iso, date) => {
          const a = byDate[iso];
          if (!a) return date;
          if (a.closed) return `${date}, ${t("closed")}`;
          return `${date}, ${t("{{available}} of {{total}} available", {
            available: a.available,
            total: a.total,
          })}`;
        }}
        renderDay={(iso) => {
          const a = byDate[iso];
          if (!a) return null;
          if (a.closed) {
            // A compact icon instead of the word: "geschlossen"/"closed" can't
            // fit a ~40px mobile day cell and used to overflow into neighbours
            // (#16). The grey styling, the day's aria-label and the legend below
            // already say "closed"; the icon is decorative (aria-hidden).
            return (
              <Lock aria-hidden className="mt-1 h-3 w-3 text-slate-400 dark:text-slate-400" />
            );
          }
          const free = a.available > 0;
          return (
            <span
              className={`mt-1 inline-flex items-center rounded-full px-1.5 py-0.5 text-[11px] font-bold ${
                free ? "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300" : "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300"
              }`}
              title={t("{{available}} of {{total}} available", { available: a.available, total: a.total })}
            >
              {a.available}
            </span>
          );
        }}
      />

      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        {t("Number = units available that day (")}
        <span className="font-semibold text-green-700 dark:text-green-300">{t("green")}</span>
        {t(" = free, ")}
        <span className="font-semibold text-red-500 dark:text-red-300">{t("red")}</span>
        {t(" = none left). Greyed “closed” days can’t be a pickup or return day, but a booking may span across them. Click a day, or drag from the start day to the end day.")}
      </p>

      <div className="mt-4">
        <p className="flex flex-wrap items-center gap-x-2 text-sm text-slate-700 dark:text-slate-200">
          {start ? (
            <>
              <span>
                {t("Selected:")} <span className="font-medium">{formatDate(start)}</span>
                {end && end !== start ? <> → <span className="font-medium">{formatDate(end)}</span></> : null}
              </span>
              <button
                type="button"
                onClick={() => {
                  setStart(null);
                  setEnd(null);
                }}
                className="text-xs font-medium text-slate-500 underline underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              >
                {t("Clear selection")}
              </button>
            </>
          ) : (
            t("Pick a start day (and optionally an end day).")
          )}
        </p>

        {maxDuration && (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {t("You can book at most {{count}} day at a time.", { count: maxDuration })}
          </p>
        )}

        {/* Once a start is picked, many users don't realise the booking can span
            more than one day — spell out that an end day is possible but optional. */}
        {start && (!end || end === start) && (
          <div className="mt-2 flex items-start gap-2 rounded-lg border border-brand-300 bg-brand-50 px-3 py-2 text-sm font-medium text-brand-800 dark:border-brand-500/40 dark:bg-brand-500/10 dark:text-brand-200">
            <Info aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" />
            <span>
              {t("You can also pick a later day as the end — you don't have to (otherwise it stays a single-day booking).")}
            </span>
          </div>
        )}

        <div className="mt-2">
          {user?.authenticated ? (
            <button
              type="button"
              onClick={addToCart}
              disabled={!start || reserving}
              className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
            >
              {reserving ? t("Adding…") : addLabel}
            </button>
          ) : (
            <button
              type="button"
              onClick={login}
              className="text-sm font-medium text-slate-700 dark:text-slate-200 underline underline-offset-2"
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
    </section>
  );
}
