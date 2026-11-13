// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { WarningNotice } from "../components/WarningNotice";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { inputCls, labelCls, primaryBtn, sectionTitleCls } from "./components/formStyles";
import { weekdayName } from "./weekdays";
import type { BusinessHours, DeskSettings } from "./types";

const FIRST_HOUR = 6;
const LAST_HOUR = 20;
const hourOptions = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => from + i);
const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;

function NumberField({
  id,
  label,
  value,
  onChange,
  min = 0,
  max,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <div>
      <label htmlFor={id} className={labelCls}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={Number.isNaN(value) ? "" : value}
        onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
        className={inputCls}
      />
    </div>
  );
}

/** Department settings: enable, assistant group, business hours per weekday,
 *  grace periods and scarcity threshold per kind, retention. */
export function DeskSettingsPage() {
  const { t } = useTranslation();
  const { pool, isAdmin } = useDesks();
  const toast = useToast();
  const { data, error } = useFetch(
    () => (isAdmin ? desksApi.settings(pool) : Promise.reject(new Error("no"))),
    [pool, isAdmin],
  );
  const groups = useFetch(
    () => (isAdmin ? desksApi.accessGroups(pool) : Promise.resolve([])),
    [pool, isAdmin],
  );
  const [form, setForm] = useState<DeskSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  if (!isAdmin) return <Navigate to="/desks" replace />;
  if (error) return <ErrorBox message={error} />;
  if (!form || !groups.data) return <Loading />;

  const poolHasGroup = groups.data.some((g) => g.in_pool);
  const set = <K extends keyof DeskSettings>(key: K, value: DeskSettings[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  function setDay(day: number, span: [number, number] | null) {
    const hours: BusinessHours = { ...(form as DeskSettings).business_hours };
    hours[String(day)] = span;
    set("business_hours", hours);
  }

  const numbersValid = [
    form.desk_grace_normal_min, form.desk_grace_short_min, form.desk_scarcity_free_below,
    form.room_grace_normal_min, form.room_grace_short_min, form.room_scarcity_free_below,
    form.retention_days,
  ].every((n) => Number.isFinite(n) && n >= 0);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setFieldError(null);
    try {
      const { pool: _pool, ...body } = form;
      void _pool;
      const saved = await desksApi.updateSettings(pool, body);
      setForm(saved);
      toast.success(t("Settings saved."));
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("The request failed.");
      setFieldError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="flex max-w-2xl flex-col gap-8">
      <section aria-labelledby="set-general">
        <h2 id="set-general" className={sectionTitleCls}>
          {t("Desksharing in this department")}
        </h2>
        <label className="mt-3 flex min-h-[44px] items-center gap-3 text-sm text-slate-900 dark:text-slate-100">
          <input
            type="checkbox"
            checked={form.enabled}
            disabled={!form.enabled && !poolHasGroup}
            onChange={(e) => set("enabled", e.target.checked)}
            className="h-5 w-5"
          />
          {t("Desksharing is enabled")}
        </label>
        {!poolHasGroup && !form.enabled && (
          <div className="mt-2">
            <WarningNotice
              message={t(
                "Enabling needs at least one access group on the department (pool). Add one in the pool settings first.",
              )}
            />
          </div>
        )}
        <div className="mt-4">
          <label htmlFor="set-assistants" className={labelCls}>
            {t("Assistant group")}
          </label>
          <select
            id="set-assistants"
            value={form.assistant_group ?? ""}
            onChange={(e) => set("assistant_group", e.target.value ? Number(e.target.value) : null)}
            className={inputCls}
          >
            <option value="">{t("No assistants")}</option>
            {groups.data.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {t("Members may mark absences and book places for others.")}
          </p>
        </div>
      </section>

      <fieldset>
        <legend className={sectionTitleCls}>{t("Business hours")}</legend>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          {t("Whole hours between 06:00 and 20:00. Closed days cannot be booked.")}
        </p>
        <ul className="flex flex-col gap-2">
          {[0, 1, 2, 3, 4, 5, 6].map((day) => {
            const span = form.business_hours[String(day)] ?? null;
            const name = weekdayName(day, "long");
            return (
              <li
                key={day}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-slate-200 p-3 dark:border-slate-700"
              >
                <span className="w-28 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {name}
                </span>
                <label className="flex min-h-[44px] items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                  <input
                    type="checkbox"
                    checked={span !== null}
                    onChange={(e) => setDay(day, e.target.checked ? [8, 18] : null)}
                    className="h-5 w-5"
                  />
                  {t("Open")}
                </label>
                {span && (
                  <span className="flex items-center gap-2">
                    <select
                      aria-label={t("{{day}}: opens", { day: name })}
                      value={span[0]}
                      onChange={(e) => {
                        const from = Number(e.target.value);
                        setDay(day, [from, Math.max(from + 1, span[1])]);
                      }}
                      className={inputCls + " !w-auto"}
                    >
                      {hourOptions(FIRST_HOUR, LAST_HOUR - 1).map((h) => (
                        <option key={h} value={h}>
                          {hh(h)}
                        </option>
                      ))}
                    </select>
                    <span aria-hidden>–</span>
                    <select
                      aria-label={t("{{day}}: closes", { day: name })}
                      value={span[1]}
                      onChange={(e) => setDay(day, [span[0], Number(e.target.value)])}
                      className={inputCls + " !w-auto"}
                    >
                      {hourOptions(span[0] + 1, LAST_HOUR).map((h) => (
                        <option key={h} value={h}>
                          {hh(h)}
                        </option>
                      ))}
                    </select>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </fieldset>

      {(
        [
          ["desk", t("Desks"), "desk"],
          ["room", t("Meeting rooms"), "room"],
        ] as const
      ).map(([key, title]) => (
        <fieldset key={key}>
          <legend className={sectionTitleCls}>{title}</legend>
          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <NumberField
              id={`set-${key}-grace-normal`}
              label={t("Grace period, normal (minutes)")}
              value={form[`${key}_grace_normal_min`]}
              onChange={(n) => set(`${key}_grace_normal_min`, n)}
              max={600}
            />
            <NumberField
              id={`set-${key}-grace-short`}
              label={t("Grace period, scarce (minutes)")}
              value={form[`${key}_grace_short_min`]}
              onChange={(n) => set(`${key}_grace_short_min`, n)}
              max={600}
            />
            <NumberField
              id={`set-${key}-scarcity`}
              label={t("Scarce when fewer than … are free")}
              value={form[`${key}_scarcity_free_below`]}
              onChange={(n) => set(`${key}_scarcity_free_below`, n)}
              max={1000}
            />
          </div>
        </fieldset>
      ))}

      <section aria-labelledby="set-retention">
        <h2 id="set-retention" className={sectionTitleCls}>
          {t("Retention")}
        </h2>
        <div className="max-w-xs">
          <NumberField
            id="set-retention-days"
            label={t("Anonymise reservation holders after (days)")}
            value={form.retention_days}
            onChange={(n) => set("retention_days", n)}
            min={1}
            max={3650}
          />
        </div>
      </section>

      {fieldError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {fieldError}
        </p>
      )}
      <div>
        <button type="submit" disabled={saving || !numbersValid} className={primaryBtn}>
          {t("Save settings")}
        </button>
      </div>
    </form>
  );
}
