// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";
import { StatsPeriodControls, useStatsPeriod } from "../components/StatsPeriod";
import { ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { useFetch } from "../useFetch";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { StatsHeatmap } from "./components/StatsHeatmap";
import { secondaryBtn, sectionTitleCls } from "./components/formStyles";
import type { PlaceKind, StatFigures } from "./types";

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toLocaleString(undefined, { maximumFractionDigits: 1 }));

function useFigureRows(): [keyof StatFigures, string][] {
  const { t } = useTranslation();
  return [
    ["booked_h", t("Booked (h)")],
    ["checked_in_h", t("Checked in (h)")],
    ["no_show_count", t("No-shows")],
    ["released_h", t("Released (h)")],
    ["rebooked_after_release_h", t("Rebooked after release (h)")],
    ["assigned_h", t("Assigned (h, fixed desks)")],
  ];
}

function QuotaCard({ kind, figures }: { kind: PlaceKind; figures: StatFigures }) {
  const { t } = useTranslation();
  const rows = useFigureRows();
  const title = kind === "desk" ? t("Desks") : t("Meeting rooms");
  return (
    <section
      aria-labelledby={`quota-${kind}`}
      className="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
    >
      <h3 id={`quota-${kind}`} className="mb-3 font-bold text-slate-900 dark:text-slate-100">
        {title}
      </h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        {rows.map(([key, label]) => (
          <div key={key}>
            <dt className="text-xs text-slate-600 dark:text-slate-300">{label}</dt>
            <dd className="text-xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
              {fmt(figures[key] as number)}
            </dd>
          </div>
        ))}
      </dl>
      <h4 className="mb-2 mt-5 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Occupancy by weekday and hour")}
      </h4>
      <StatsHeatmap data={figures.heatmap} title={t("Occupancy of {{kind}}", { kind: title })} />
    </section>
  );
}

/** Anonymous usage statistics of the department: quota per kind, heatmap,
 *  special places, CSV export. */
export function DeskStatsPage() {
  const { t } = useTranslation();
  const { pool, isAdmin } = useDesks();
  const toast = useToast();
  const period = useStatsPeriod(30);
  const { from, to } = period;
  const rows = useFigureRows();
  const [exporting, setExporting] = useState(false);
  const periodOk = period.draftError === null;
  const { data, loading, error } = useFetch(
    () => (isAdmin ? desksApi.stats(pool, from, to) : Promise.reject(new Error("no"))),
    [pool, from, to, isAdmin],
  );

  if (!isAdmin) return <Navigate to="/desks" replace />;

  async function exportCsv() {
    setExporting(true);
    try {
      const blob = await desksApi.statsCsv(pool, from, to);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `desksharing-stats-${from}-${to}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <StatsPeriodControls period={period}>
        <button type="button" onClick={exportCsv} disabled={exporting || !periodOk} className={secondaryBtn}>
          <Download aria-hidden className="h-4 w-4" />
          {t("Download CSV")}
        </button>
      </StatsPeriodControls>
      {error && <ErrorBox message={error} />}
      {loading && <Loading />}
      {data && (
        <div className="flex flex-col gap-6">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t("Standard places are counted as a quota per kind; no person data is included.")}
          </p>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <QuotaCard kind="desk" figures={data.quota.desk} />
            <QuotaCard kind="meeting_room" figures={data.quota.meeting_room} />
          </div>
          <section aria-labelledby="special-title">
            <h2 id="special-title" className={sectionTitleCls}>
              {t("Special places")}
            </h2>
            {data.special.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {t("No places are flagged as special.")}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="mt-2 min-w-full text-sm">
                  <caption className="sr-only">{t("Special places")}</caption>
                  <thead>
                    <tr className="text-left text-xs text-slate-600 dark:text-slate-300">
                      <th scope="col" className="py-2 pr-4 font-semibold">
                        {t("Place")}
                      </th>
                      {rows.map(([key, label]) => (
                        <th key={key} scope="col" className="px-2 py-2 text-right font-semibold">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.special.map((s) => (
                      <tr key={s.place.id} className="border-t border-slate-200 dark:border-slate-700">
                        <th scope="row" className="py-2 pr-4 text-left font-semibold text-slate-900 dark:text-slate-100">
                          {s.place.name}
                        </th>
                        {rows.map(([key]) => (
                          <td key={key} className="px-2 py-2 text-right tabular-nums text-slate-800 dark:text-slate-200">
                            {fmt(s[key] as number)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
