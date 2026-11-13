// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Repeat } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDate } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { ReservationCard } from "./components/ReservationCard";
import { SeriesConflicts } from "./components/SeriesConflicts";
import { berlinNow } from "./time";
import { addDays, pad2, weekdayName } from "./weekdays";
import type { SeriesConflict } from "./types";

const EXTEND_WINDOW_DAYS = 28;

/** One recurring series: place, weekdays, hours, validity, upcoming
 *  occurrences, "extend" and "end series". */
export function SeriesPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const seriesId = Number(id);
  const navigate = useNavigate();
  const location = useLocation();
  const confirm = useConfirm();
  const toast = useToast();
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [conflicts, setConflicts] = useState<SeriesConflict[]>(
    (location.state as { conflicts?: SeriesConflict[] } | null)?.conflicts ?? [],
  );
  // Bumped to remount the conflict list when a new set arrives.
  const [conflictKey, setConflictKey] = useState(0);
  const changed = () => setReload((n) => n + 1);

  const all = useFetch(() => desksApi.mySeries(), [reload]);
  const mine = useFetch(() => desksApi.myReservations(), [reload]);
  const series = all.data?.find((s) => s.id === seriesId);
  const occurrences = (mine.data ?? []).filter((r) => r.series_id === seriesId);

  const today = berlinNow().date;
  const canExtend = !!series && today >= addDays(series.valid_until, -EXTEND_WINDOW_DAYS);
  const ended = !!series && series.valid_until < today;

  async function extend() {
    setBusy(true);
    try {
      const res = await desksApi.extendSeries(seriesId);
      toast.success(t("Series extended."));
      setConflicts(res.conflicts);
      setConflictKey((k) => k + 1);
      changed();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    const ok = await confirm({
      message: t(
        "End this series? All upcoming occurrences are cancelled. Past occurrences stay.",
      ),
      confirmLabel: t("End series"),
      cancelLabel: t("Keep"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await desksApi.cancelSeries(seriesId);
      toast.success(t("Series ended."));
      navigate("/desks/mine");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      setBusy(false);
    }
  }

  const btn =
    "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

  return (
    <section aria-labelledby="series-title">
      <Link
        to="/desks/mine"
        className="mb-3 inline-flex min-h-[44px] items-center gap-1.5 text-sm font-medium text-slate-700 hover:underline dark:text-slate-200"
      >
        <ArrowLeft aria-hidden className="h-4 w-4" />
        {t("My reservations")}
      </Link>

      {(all.loading || mine.loading) && !series && <Loading />}
      {all.error && <ErrorBox message={all.error} />}
      {all.data && !series && <Empty icon={Repeat} label={t("This series does not exist.")} />}

      {series && (
        <>
          <div className="mb-6 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
            <h2
              id="series-title"
              className="flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100"
            >
              <Repeat aria-hidden className="h-5 w-5 text-brand-600 dark:text-brand-400" />
              {series.place.name}
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {[series.place.building, series.place.floor, series.place.room]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <p className="mt-2 text-sm text-slate-900 dark:text-slate-100">
              {t("Weekly on {{days}}", { days: series.weekdays.map((d) => weekdayName(d)).join(", ") })},{" "}
              {pad2(series.start_hour)}:00–{pad2(series.end_hour)}:00
            </p>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {t("Valid {{from}} to {{until}}", {
                from: formatDate(series.valid_from),
                until: formatDate(series.valid_until),
              })}
            </p>
            {series.comment && (
              <p className="mt-1 break-words text-sm italic text-slate-700 dark:text-slate-200">
                {series.comment}
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {canExtend && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={extend}
                  className="min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 hover:bg-brand-400 disabled:opacity-50"
                >
                  {t("Extend by 3 months")}
                </button>
              )}
              <button type="button" disabled={busy} onClick={end} className={btn}>
                {t("End series")}
              </button>
            </div>
            {!canExtend && (
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
                {t("You can extend the series from {{date}}.", {
                  date: formatDate(addDays(series.valid_until, -EXTEND_WINDOW_DAYS)),
                })}
              </p>
            )}
            {ended && (
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
                {t("This series has ended. Extending starts today.")}
              </p>
            )}
          </div>

          <SeriesConflicts
            key={conflictKey}
            seriesId={seriesId}
            conflicts={
              // After a reload the router state still carries settled dates.
              mine.data ? conflicts.filter((c) => !occurrences.some((o) => o.day === c.day)) : []
            }
            onDone={(day, booked) => {
              setConflicts((cs) => cs.filter((c) => c.day !== day));
              if (booked) changed();
            }}
          />

          <h3 className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">
            {t("Upcoming occurrences")}
          </h3>
          {mine.error && <ErrorBox message={mine.error} />}
          {mine.data && occurrences.length === 0 && (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {t("There are no upcoming occurrences.")}
            </p>
          )}
          <ul className="space-y-2">
            {occurrences.map((r) => (
              <ReservationCard key={r.id} reservation={r} onChanged={changed} showDay />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
