// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatDayWithWeekday } from "../../dates";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { SeriesConflict } from "../types";

interface Props {
  seriesId: number;
  conflicts: SeriesConflict[];
  /** A date is settled (`booked`: an alternative was booked, else skipped); the
   *  parent drops it from the list (and reloads when booked). */
  onDone: (day: string, booked: boolean) => void;
}

/** Dates of a series that could not be booked at its place: per date the
 *  alternatives as one-tap cards, or "skip" to leave the date out. */
export function SeriesConflicts({ seriesId, conflicts, onDone }: Props) {
  const { t } = useTranslation();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const open = conflicts;
  if (open.length === 0) return null;

  async function pick(day: string, placeId: number) {
    setBusy(true);
    try {
      await desksApi.resolveSeries(seriesId, day, placeId);
      toast.success(t("Booked."));
      onDone(day, true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-labelledby="series-conflicts"
      className="mb-6 rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <h2 id="series-conflicts" className="text-base font-bold">
        {t("{{count}} dates could not be booked at this place", { count: open.length })}
      </h2>
      <p className="mt-1 text-sm">{t("Choose another place for a date or skip it.")}</p>
      <ul className="mt-3 space-y-4">
        {open.map((c) => (
          <li key={c.day}>
            <p className="font-medium">{formatDayWithWeekday(c.day)}</p>
            {c.alternatives.length === 0 && (
              <p className="text-sm">{t("No other place is free on this date.")}</p>
            )}
            <ul className="mt-2 space-y-2">
              {c.alternatives.map((alt) => (
                <li key={alt.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => pick(c.day, alt.id)}
                    className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-amber-400 bg-white px-3 py-2 text-left text-slate-900 hover:bg-amber-100 disabled:opacity-50 dark:bg-slate-900 dark:text-slate-100"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{alt.name}</span>
                      <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                        {[alt.floor, alt.room].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className="shrink-0 text-sm font-semibold">{t("Book this")}</span>
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              disabled={busy}
              onClick={() => onDone(c.day, false)}
              className="mt-2 min-h-[44px] rounded-full border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
            >
              {t("Skip this date")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
