// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Link2, Repeat, Trash2 } from "lucide-react";
import { formatDate, formatDayWithWeekday } from "../../dates";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Reservation, Series } from "../types";
import { pad2, weekdayName } from "../weekdays";
import { ReservationCard } from "./ReservationCard";

const btnIcon =
  "inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

interface Props {
  series: Series;
  /** The series' upcoming own reservations, ordered by start. */
  occurrences: Reservation[];
  /** Reservation ids just booked: their group starts expanded. */
  justBooked: Set<number>;
  onChanged: () => void;
}

/** A recurring booking as a group: summary row with manage/delete actions,
 *  the upcoming dates as cards when expanded. */
export function SeriesGroup({ series: sr, occurrences, justBooked, onChanged }: Props) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const [expanded, setExpanded] = useState(() => occurrences.some((o) => justBooked.has(o.id)));
  const [busy, setBusy] = useState(false);
  const listId = `series-${sr.id}-dates`;
  const next = occurrences[0];

  async function remove() {
    const ok = await confirm({
      title: t("Delete series?"),
      message: t("Delete the series at {{place}}? Upcoming dates are deleted. Past dates stay.", {
        place: sr.place.name,
      }),
      confirmLabel: t("Delete"),
      cancelLabel: t("Keep"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await desksApi.cancelSeries(sr.id);
      toast.success(t("Series deleted."));
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const toggleLabel = expanded ? t("Hide dates") : t("Show dates");
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <li className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2 p-3">
        <Repeat aria-hidden className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-400" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
            {sr.place.name} · {sr.weekdays.map((d) => weekdayName(d)).join(", ")} {pad2(sr.start_hour)}–
            {pad2(sr.end_hour)}
          </p>
          <p className="truncate text-xs text-slate-600 dark:text-slate-300">
            {t("until {{date}}", { date: formatDate(sr.valid_until) })}
            {next && ` · ${t("Next: {{date}}", { date: formatDayWithWeekday(next.day) })}`}
          </p>
        </div>
        <Link to={`/desks/series/${sr.id}`} aria-label={t("Manage series")} title={t("Manage series")} className={btnIcon}>
          <Link2 aria-hidden className="h-4 w-4" />
        </Link>
        <button
          type="button"
          disabled={busy}
          onClick={remove}
          aria-label={t("Delete series")}
          title={t("Delete series")}
          className={btnIcon}
        >
          <Trash2 aria-hidden className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-controls={listId}
          aria-label={toggleLabel}
          title={toggleLabel}
          className={btnIcon}
        >
          <Chevron aria-hidden className="h-4 w-4" />
        </button>
      </div>
      {expanded && (
        <ul id={listId} className="space-y-2 border-t border-slate-200 p-3 dark:border-slate-800">
          {occurrences.map((r) => (
            <ReservationCard key={r.id} reservation={r} onChanged={onChanged} justBooked={justBooked.has(r.id)} inSeries />
          ))}
        </ul>
      )}
    </li>
  );
}
