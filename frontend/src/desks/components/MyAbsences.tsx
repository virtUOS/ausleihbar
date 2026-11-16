// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarRange, ChevronDown, ChevronRight } from "lucide-react";
import { formatDate } from "../../dates";
import { useFetch } from "../../useFetch";
import { MultiDayCalendar } from "../../components/MultiDayCalendar";
import { ErrorBox } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { normalizeRanges, rangesContain, type DayRange } from "../../dayRanges";
import { desksApi } from "../api";
import { planAbsenceChanges } from "../absencePlan";
import { addMonths, isoOf } from "../weekdays";
import { primaryBtn, secondaryBtn } from "./formStyles";

/** The person's own absences as a collapsible section. Editing happens in a
 *  multi-range calendar; saving removes dropped periods, then creates new
 *  ones (`planAbsenceChanges`). Adding releases one's reservations in the
 *  period; no reason or kind is stored. Absences entered by assistants show
 *  in the list too (not editable here), so the person sees why reservations
 *  were released. */
export function MyAbsences({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [reload, setReload] = useState(0);
  /** null = follow the default (open when there are absences). */
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const [draft, setDraft] = useState<DayRange[] | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, error } = useFetch(() => desksApi.absences(), [reload]);

  const today = isoOf(new Date());
  const maxDay = addMonths(today, 12);
  const count = data?.length ?? 0;
  const isOpen = draft !== null || (expanded ?? count > 0);
  const own = (data ?? []).filter((a) => a.self_entered && a.end_date >= today);
  const foreign = normalizeRanges(
    (data ?? [])
      .filter((a) => !a.self_entered && a.end_date >= today)
      .map((a) => ({ start: a.start_date < today ? today : a.start_date, end: a.end_date })),
  );

  function startEdit() {
    setDraft(
      normalizeRanges(own.map((a) => ({ start: a.start_date < today ? today : a.start_date, end: a.end_date }))),
    );
  }

  async function save() {
    if (!draft) return;
    const plan = planAbsenceChanges(own, draft, today, foreign);
    if (plan.remove.length === 0 && plan.create.length === 0) {
      setDraft(null);
      return;
    }
    setBusy(true);
    let released = 0;
    let kept = 0;
    try {
      for (const id of plan.remove) kept += (await desksApi.deleteAbsence(id)).kept_bookings;
      for (const r of plan.create) {
        const created = await desksApi.createAbsence({ start_date: r.start, end_date: r.end });
        released += created.released_count;
      }
      const base =
        released > 0
          ? t("Absence saved. {{count}} reservations released.", { count: released })
          : t("Absences saved.");
      if (kept > 0) {
        toast.warning(
          `${base} ${t("Others booked your fixed desk for {{count}} reservations; they stay valid.", { count: kept })}`,
        );
      } else toast.success(base);
      setDraft(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    } finally {
      setBusy(false);
      setReload((n) => n + 1);
      onChanged();
    }
  }

  const Chevron = isOpen ? ChevronDown : ChevronRight;

  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          aria-expanded={isOpen}
          disabled={draft !== null}
          onClick={() => setExpanded(!isOpen)}
          className="flex min-h-[44px] min-w-0 flex-1 items-center gap-2 text-left text-sm font-bold text-slate-900 dark:text-slate-100"
        >
          <Chevron aria-hidden className="h-4 w-4 shrink-0" />
          <span>
            {t("Absences")} ({count})
          </span>
        </button>
        {draft === null && (
          <button
            type="button"
            aria-label={t("Edit absences")}
            title={t("Edit absences")}
            onClick={() => {
              startEdit();
              setExpanded(true);
            }}
            className={secondaryBtn + " !h-11 !w-11 !px-0"}
          >
            <CalendarRange aria-hidden className="h-4 w-4" />
          </button>
        )}
      </div>
      {error && <ErrorBox message={error} />}
      {isOpen && draft === null && data && data.length > 0 && (
        <ul className="space-y-2">
          {data.map((a) => (
            <li
              key={a.id}
              className="flex min-h-[44px] items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
            >
              <span className="min-w-0 flex-1 text-sm text-slate-900 dark:text-slate-100">
                {formatDate(a.start_date)} – {formatDate(a.end_date)}
                {!a.self_entered && (
                  <span className="ml-2 text-xs text-slate-600 dark:text-slate-300">{t("entered by the department")}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {draft !== null && (
        <div className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <MultiDayCalendar
            value={draft}
            onChange={setDraft}
            minDay={today}
            maxDay={maxDay}
            isDisabled={(iso) => rangesContain(foreign, iso)}
          />
          <p className="text-xs text-slate-600 dark:text-slate-300">
            {t("Your reservations in this period are released.")}
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={save} className={primaryBtn}>
              {t("Save")}
            </button>
            <button type="button" disabled={busy} onClick={() => setDraft(null)} className={secondaryBtn}>
              {t("Cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
