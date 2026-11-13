// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { inputCls, labelCls } from "./formStyles";

/** "From" / "Until" day fields of an absence (whole days, inclusive). Moving
 *  the start past the end pulls the end along. Shared by the own-vacation
 *  section and the assistants' absences page. */
export function AbsencePeriodFields({
  idPrefix,
  start,
  end,
  onChange,
}: {
  idPrefix: string;
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${idPrefix}-start`} className={labelCls}>
            {t("From")}
          </label>
          <input
            id={`${idPrefix}-start`}
            type="date"
            value={start}
            onChange={(e) => onChange(e.target.value, end < e.target.value ? e.target.value : end)}
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-end`} className={labelCls}>
            {t("Until")}
          </label>
          <input
            id={`${idPrefix}-end`}
            type="date"
            value={end}
            min={start || undefined}
            onChange={(e) => onChange(start, e.target.value)}
            className={inputCls}
          />
        </div>
      </div>
      {end < start && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          {t("The end date must not be before the start date.")}
        </p>
      )}
    </>
  );
}

/** Whether a period from these fields can be submitted. */
export function absencePeriodValid(start: string, end: string): boolean {
  return Boolean(start && end) && end >= start;
}
