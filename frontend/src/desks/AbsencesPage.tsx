// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarOff, Trash2 } from "lucide-react";
import { useAuth } from "../auth";
import { formatDate } from "../dates";
import { useFetch } from "../useFetch";
import { useConfirm } from "../components/ConfirmDialog";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { PersonPicker } from "./components/PersonPicker";
import { dangerBtn, inputCls, labelCls, primaryBtn, sectionTitleCls } from "./components/formStyles";
import { isoOf } from "./weekdays";
import type { AbsenceKind, PersonChoice } from "./types";

/** Absences of department members (assistants and department admins): list,
 *  add (person by name, period, kind) and delete. No reason is stored. */
export function AbsencesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { pool } = useDesks();
  const toast = useToast();
  const confirm = useConfirm();
  const [reload, setReload] = useState(0);
  const [person, setPerson] = useState<PersonChoice | null>(null);
  const [kind, setKind] = useState<AbsenceKind>("vacation");
  const [start, setStart] = useState(isoOf(new Date()));
  const [end, setEnd] = useState(isoOf(new Date()));
  const [busy, setBusy] = useState(false);
  const allowed = (user?.desk_assistant_pool_ids ?? []).includes(pool);
  const { data, error } = useFetch(
    () => (allowed ? desksApi.manageAbsences() : Promise.resolve([])),
    [allowed, reload],
  );

  if (!allowed) return <Navigate to="/desks" replace />;

  const kindLabel = (k: AbsenceKind) => (k === "vacation" ? t("Vacation") : t("Absent"));
  const invalid = !person || !start || !end || end < start;

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!person || invalid) return;
    setBusy(true);
    try {
      await desksApi.createManageAbsence({ user: person.id, start_date: start, end_date: end, kind });
      toast.success(t("Absence added."));
      setPerson(null);
      setReload((n) => n + 1);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number, name: string) {
    const ok = await confirm({
      title: t("Delete absence"),
      message: t("Delete the absence of {{name}}? Released places are not restored.", { name }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deleteManageAbsence(id);
      toast.success(t("Absence deleted."));
      setReload((n) => n + 1);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="abs-add">
        <h2 id="abs-add" className={sectionTitleCls}>
          {t("Mark someone absent")}
        </h2>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Reservations of that person in the period are released. No reason is stored.")}
        </p>
        <form onSubmit={add} className="flex max-w-xl flex-col gap-4">
          <PersonPicker pool={pool} value={person} onChange={setPerson} label={t("Person")} />
          <div>
            <label htmlFor="abs-kind" className={labelCls}>
              {t("Kind")}
            </label>
            <select
              id="abs-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as AbsenceKind)}
              className={inputCls}
            >
              <option value="vacation">{t("Vacation")}</option>
              <option value="absent">{t("Absent")}</option>
            </select>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="abs-start" className={labelCls}>
                {t("From")}
              </label>
              <input
                id="abs-start"
                type="date"
                value={start}
                onChange={(e) => {
                  setStart(e.target.value);
                  if (end < e.target.value) setEnd(e.target.value);
                }}
                className={inputCls}
              />
            </div>
            <div>
              <label htmlFor="abs-end" className={labelCls}>
                {t("Until")}
              </label>
              <input
                id="abs-end"
                type="date"
                value={end}
                min={start || undefined}
                onChange={(e) => setEnd(e.target.value)}
                className={inputCls}
              />
            </div>
          </div>
          {end < start && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
              {t("The end date must not be before the start date.")}
            </p>
          )}
          <div>
            <button type="submit" disabled={busy || invalid} className={primaryBtn}>
              {t("Add absence")}
            </button>
          </div>
        </form>
      </section>

      <section aria-labelledby="abs-list">
        <h2 id="abs-list" className={sectionTitleCls}>
          {t("Current and upcoming absences")}
        </h2>
        {error && <ErrorBox message={error} />}
        {!data && !error && <Loading />}
        {data && data.length === 0 && <Empty icon={CalendarOff} label={t("No absences.")} />}
        {data && data.length > 0 && (
          <ul className="mt-3 flex flex-col gap-2">
            {data.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-slate-900 dark:text-slate-100">
                    {a.user_name}
                  </p>
                  <p className="text-xs text-slate-600 dark:text-slate-300">
                    {kindLabel(a.kind)} · {formatDate(a.start_date)} – {formatDate(a.end_date)}
                  </p>
                </div>
                <button
                  type="button"
                  aria-label={t("Delete absence of {{name}}", { name: a.user_name })}
                  onClick={() => remove(a.id, a.user_name)}
                  className={dangerBtn + " !px-3"}
                >
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
