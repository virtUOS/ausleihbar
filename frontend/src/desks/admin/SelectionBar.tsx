// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { primaryBtn, secondaryBtn } from "../components/formStyles";

/** Sticky bar while rooms or places are selected (app admins): how many, and
 *  what can be done with them. */
export function SelectionBar({
  rooms,
  places,
  onAssign,
  onClear,
}: {
  rooms: number;
  places: number;
  onAssign: () => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="region"
      aria-label={t("Selection")}
      className="sticky bottom-4 z-20 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-900"
    >
      <p aria-live="polite" className="min-w-0 flex-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {rooms > 0 && places > 0
          ? t("{{rooms}}, {{places}} selected", {
              rooms: t("{{count}} rooms", { count: rooms }),
              places: t("{{count}} places", { count: places }),
            })
          : rooms > 0
            ? t("{{count}} rooms selected", { count: rooms })
            : t("{{count}} places selected", { count: places })}
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onAssign} className={primaryBtn}>
          {t("Assign department")}
        </button>
        <button type="button" onClick={onClear} className={secondaryBtn}>
          {t("Clear selection")}
        </button>
      </div>
    </div>
  );
}
