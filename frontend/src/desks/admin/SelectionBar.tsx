// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { primaryBtn, secondaryBtn } from "../components/formStyles";

/** Sticky bar while rooms or places are selected (app admins): how many, and
 *  what can be done with them. */
export function SelectionBar({
  rooms,
  places,
  onAssign,
  onUnassign,
  onClear,
}: {
  rooms: number;
  places: number;
  onAssign: () => void;
  /** Remove the department assignment of the selection. */
  onUnassign: () => void;
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
      {/* Clearing as an icon beside the count keeps the bar low on phones. */}
      <button
        type="button"
        onClick={onClear}
        aria-label={t("Clear selection")}
        title={t("Clear selection")}
        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 hover:text-slate-900 sm:order-last dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        <X aria-hidden className="h-5 w-5" />
      </button>
      <div className="flex w-full flex-wrap gap-2 sm:w-auto">
        <button type="button" onClick={onAssign} className={primaryBtn}>
          {t("Assign department")}
        </button>
        <button type="button" onClick={onUnassign} className={secondaryBtn}>
          {t("Remove assignment")}
        </button>
      </div>
    </div>
  );
}
