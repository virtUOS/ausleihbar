// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { weekdayName } from "../weekdays";
import type { Heatmap } from "../types";

/** Opaque pale-to-strong amber, so the dark text stays readable in light and
 *  dark mode alike. */
function heat(pct: number): string {
  const k = Math.min(Math.max(pct, 0), 100) / 100;
  const from = [254, 246, 220];
  const to = [240, 165, 0];
  const c = from.map((f, i) => Math.round(f + (to[i] - f) * k));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** Occupancy per weekday x hour. The grid is a visual aid (aria-hidden); the
 *  same numbers are available as a table for screen readers. Colour is not
 *  the only carrier: every cell shows its percentage. */
export function StatsHeatmap({ data, title }: { data: Heatmap; title: string }) {
  const { t } = useTranslation();
  const weekdays = Object.keys(data).map(Number).sort((a, b) => a - b);
  const hourSet = new Set<number>();
  for (const wd of weekdays) for (const h of Object.keys(data[String(wd)])) hourSet.add(Number(h));
  const hours = [...hourSet].sort((a, b) => a - b);
  if (weekdays.length === 0) {
    return <p className="text-sm text-slate-600 dark:text-slate-300">{t("No data in this period.")}</p>;
  }
  const cell = (wd: number, h: number): number | null => data[String(wd)]?.[String(h)] ?? null;
  return (
    <div>
      <div aria-hidden className="overflow-x-auto pb-1">
        <table className="border-separate border-spacing-0.5 text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-white pr-2 dark:bg-slate-900" />
              {hours.map((h) => (
                <th key={h} className="min-w-[2.25rem] text-center font-normal text-slate-600 dark:text-slate-300">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weekdays.map((wd) => (
              <tr key={wd}>
                <th className="sticky left-0 bg-white pr-2 text-left font-semibold text-slate-700 dark:bg-slate-900 dark:text-slate-200">
                  {weekdayName(wd)}
                </th>
                {hours.map((h) => {
                  const v = cell(wd, h);
                  return (
                    <td
                      key={h}
                      className={`h-9 rounded text-center ${
                        v === null
                          ? "bg-slate-50 text-slate-300 dark:bg-slate-800/40 dark:text-slate-600"
                          : "text-slate-900"
                      }`}
                      style={
                        v === null
                          ? undefined
                          : { backgroundColor: heat(v) }
                      }
                    >
                      {v === null ? "·" : Math.round(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {t("Occupancy in percent per weekday (rows) and hour (columns).")}
        </p>
      </div>
      <table className="sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">{t("Weekday")}</th>
            <th scope="col">{t("Hour")}</th>
            <th scope="col">{t("Occupancy (%)")}</th>
          </tr>
        </thead>
        <tbody>
          {weekdays.flatMap((wd) =>
            hours
              .filter((h) => cell(wd, h) !== null)
              .map((h) => (
                <tr key={`${wd}-${h}`}>
                  <th scope="row">{weekdayName(wd, "long")}</th>
                  <td>{h}:00</td>
                  <td>{cell(wd, h)}</td>
                </tr>
              )),
          )}
        </tbody>
      </table>
    </div>
  );
}
