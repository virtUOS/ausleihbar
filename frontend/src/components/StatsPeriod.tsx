// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import i18n from "../i18n";
import { formatDate } from "../dates";

export const RANGES = [
  { days: 30, label: i18n.t("30 days") },
  { days: 90, label: i18n.t("90 days") },
  { days: 365, label: i18n.t("12 months") },
];

export const DEFAULT_RANGE = 90;
const MAX_YEARS = 5;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** A local date as `YYYY-MM-DD`, the year zero-padded (works below 1000). */
export function toIsoDate(d: Date): string {
  const pad = (n: number, len = 2) => String(n).padStart(len, "0");
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** A local Date for y-m-d; `setFullYear` so years 0–99 are not read as 19xx. */
function localDate(y: number, monthIndex: number, day: number): Date {
  const d = new Date(2000, 0, 1);
  d.setFullYear(y, monthIndex, day);
  return d;
}

export function isIsoDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  return toIsoDate(localDate(y, m - 1, d)) === value;
}

/** `iso` plus `years`, clamped to the month's last day (29 Feb → 28 Feb),
 *  like the backend's month arithmetic. */
export function addYears(iso: string, years: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const last = localDate(y + years, m, 0).getDate();
  return toIsoDate(localDate(y + years, m - 1, Math.min(d, last)));
}

/** Inline hint for an invalid custom period, null when it is valid. */
export function periodError(from: string, to: string): string | null {
  if (!isIsoDate(from) || !isIsoDate(to)) return i18n.t("Please enter a start and an end date.");
  if (to < from) return i18n.t("The end date must not be before the start date.");
  if (to > addYears(from, MAX_YEARS)) return i18n.t("The period may span at most 5 years.");
  return null;
}

export function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return toIsoDate(d);
}


export interface StatsPeriod {
  params: URLSearchParams;
  /** Change the URL query (replace, keeps history clean). */
  updateParams: (change: (next: URLSearchParams) => void) => void;
  days: number;
  custom: boolean;
  from: string;
  to: string;
  draftFrom: string;
  draftTo: string;
  draftError: string | null;
  chooseRange: (value: number) => void;
  chooseCustom: () => void;
  editDraft: (from: string, to: string) => void;
}

/** Period state of a statistics page, kept in the URL: `?range=30|90|365` or
 *  `?from=&to=`. Only a valid custom period is written to the URL (and so
 *  fetched); invalid drafts stay local with an inline error. */
export function useStatsPeriod(defaultRange = DEFAULT_RANGE): StatsPeriod {
  const [params, setParams] = useSearchParams();
  const rangeParam = Number(params.get("range"));
  const days = RANGES.some((r) => r.days === rangeParam) ? rangeParam : defaultRange;
  const custom = params.has("from") || params.has("to");
  const urlFrom = params.get("from") ?? "";
  const urlTo = params.get("to") ?? "";
  const customValid = custom && periodError(urlFrom, urlTo) === null;

  const today = toIsoDate(new Date());
  const to = customValid ? urlTo : today;
  const from = customValid ? urlFrom : isoDaysAgo(days);

  const [draftFrom, setDraftFrom] = useState(urlFrom);
  const [draftTo, setDraftTo] = useState(urlTo);
  useEffect(() => {
    setDraftFrom(urlFrom);
    setDraftTo(urlTo);
  }, [urlFrom, urlTo]);
  const draftError = custom ? periodError(draftFrom, draftTo) : null;

  const updateParams = (change: (next: URLSearchParams) => void) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        change(next);
        return next;
      },
      { replace: true },
    );
  const chooseRange = (value: number) =>
    updateParams((next) => {
      next.delete("from");
      next.delete("to");
      if (value === defaultRange) next.delete("range");
      else next.set("range", String(value));
    });
  const chooseCustom = () =>
    updateParams((next) => {
      next.delete("range");
      next.set("from", from);
      next.set("to", to);
    });
  const editDraft = (nextFrom: string, nextTo: string) => {
    setDraftFrom(nextFrom);
    setDraftTo(nextTo);
    if (periodError(nextFrom, nextTo) === null) {
      updateParams((next) => {
        next.set("from", nextFrom);
        next.set("to", nextTo);
      });
    }
  };
  return {
    params, updateParams, days, custom, from, to,
    draftFrom, draftTo, draftError, chooseRange, chooseCustom, editDraft,
  };
}

/** Period pills (30 days / 90 days / 12 months / custom) with the date row of
 *  a custom period; `children` (e.g. a pool select) sit in the first row. */
export function StatsPeriodControls({
  period: p,
  children,
}: {
  period: StatsPeriod;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1">
          {RANGES.map((r) => (
            <button
              key={r.days}
              type="button"
              onClick={() => p.chooseRange(r.days)}
              aria-pressed={!p.custom && p.days === r.days}
              className={`min-h-[44px] rounded-full px-3 py-1 text-sm sm:min-h-0 ${
                !p.custom && p.days === r.days
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {r.label}
            </button>
          ))}
          <button
            type="button"
            onClick={p.chooseCustom}
            aria-pressed={p.custom}
            className={`min-h-[44px] rounded-full px-3 py-1 text-sm sm:min-h-0 ${
              p.custom
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {t("Custom period")}
          </button>
        </div>
        {children}
        <span className="text-xs text-slate-400 dark:text-slate-300">
          {formatDate(p.from)} – {formatDate(p.to)}
        </span>
      </div>

      {p.custom && (
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-600 dark:text-slate-300">
            {t("From")}
            <input
              type="date"
              value={p.draftFrom}
              max={p.draftTo || undefined}
              onChange={(e) => p.editDraft(e.target.value, p.draftTo)}
              aria-invalid={p.draftError !== null}
              aria-describedby={p.draftError ? "stats-period-error" : undefined}
              className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            />
          </label>
          <label className="text-xs text-slate-600 dark:text-slate-300">
            {t("Until")}
            <input
              type="date"
              value={p.draftTo}
              min={p.draftFrom || undefined}
              max={isIsoDate(p.draftFrom) ? addYears(p.draftFrom, MAX_YEARS) : undefined}
              onChange={(e) => p.editDraft(p.draftFrom, e.target.value)}
              aria-invalid={p.draftError !== null}
              aria-describedby={p.draftError ? "stats-period-error" : undefined}
              className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            />
          </label>
          {p.draftError && (
            <p id="stats-period-error" role="alert" className="pb-1.5 text-xs text-red-600 dark:text-red-400">
              {p.draftError}
            </p>
          )}
        </div>
      )}
    </>
  );
}
