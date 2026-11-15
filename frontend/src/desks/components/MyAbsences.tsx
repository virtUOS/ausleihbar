// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import { formatDate } from "../../dates";
import { useFetch } from "../../useFetch";
import { useConfirm } from "../../components/ConfirmDialog";
import { ErrorBox } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { isoOf } from "../weekdays";
import { AbsencePeriodFields, absencePeriodValid } from "./AbsencePeriodFields";
import { dangerBtn, secondaryBtn } from "./formStyles";

/** The person's own absences: list, add, delete. Adding releases one's
 *  reservations in the period; no reason or kind is stored. Absences entered
 *  by assistants show here too (not deletable here), so the person sees why
 *  reservations were released. */
export function MyAbsences({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState(isoOf(new Date()));
  const [end, setEnd] = useState(isoOf(new Date()));
  const [busy, setBusy] = useState(false);
  const { data, error } = useFetch(() => desksApi.absences(), [reload]);

  const refresh = () => {
    setReload((n) => n + 1);
    onChanged();
  };

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!absencePeriodValid(start, end)) return;
    setBusy(true);
    try {
      const created = await desksApi.createAbsence({ start_date: start, end_date: end });
      toast.success(
        created.released_count > 0
          ? t("Absence saved. {{count}} reservations released.", { count: created.released_count })
          : t("Absence saved."),
      );
      setOpen(false);
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    const ok = await confirm({
      title: t("Delete absence"),
      message: t("Delete this absence? Released reservations are not restored."),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      const { kept_bookings } = await desksApi.deleteAbsence(id);
      if (kept_bookings > 0) {
        toast.warning(
          t("Absence deleted. Others booked your fixed desk for {{count}} reservations; they stay valid.", {
            count: kept_bookings,
          }),
        );
      } else toast.success(t("Absence deleted."));
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    }
  }

  return (
    <div className="mb-6">
      <h3 className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">{t("My absences")}</h3>
      {error && <ErrorBox message={error} />}
      {data && data.length > 0 && (
        <ul className="mb-2 space-y-2">
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
              {a.self_entered && (
                <button
                  type="button"
                  aria-label={t("Delete absence {{start}} – {{end}}", {
                    start: formatDate(a.start_date),
                    end: formatDate(a.end_date),
                  })}
                  onClick={() => remove(a.id)}
                  className={dangerBtn + " !px-3"}
                >
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <form
          onSubmit={add}
          className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800"
        >
          <AbsencePeriodFields
            idPrefix="abs-own"
            start={start}
            end={end}
            onChange={(s, e) => {
              setStart(s);
              setEnd(e);
            }}
          />
          <p className="text-xs text-slate-600 dark:text-slate-300">
            {t("Your reservations in this period are released.")}
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={busy || !absencePeriodValid(start, end)} className={secondaryBtn}>
              {t("Save absence")}
            </button>
            <button type="button" onClick={() => setOpen(false)} className={secondaryBtn}>
              {t("Cancel")}
            </button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setOpen(true)} className={secondaryBtn}>
          {t("Add absence")}
        </button>
      )}
    </div>
  );
}
