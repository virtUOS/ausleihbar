// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

export type SortMode = "manual" | "alpha";

/** Small pill toggle to switch a shop list between the grouped (curated) order
 *  and A–Z. */
export function SortToggle({
  value,
  onChange,
}: {
  value: SortMode;
  onChange: (mode: SortMode) => void;
}) {
  const { t } = useTranslation();
  const base =
    "rounded-full px-2.5 py-1 text-xs font-semibold transition-colors duration-150";
  return (
    <div
      role="group"
      aria-label={t("Sort order")}
      className="inline-flex gap-0.5 rounded-full bg-slate-100 p-0.5 dark:bg-slate-800"
    >
      <button
        type="button"
        onClick={() => onChange("manual")}
        aria-pressed={value === "manual"}
        className={`${base} ${
          value === "manual"
            ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
        }`}
      >
        {t("Grouped")}
      </button>
      <button
        type="button"
        onClick={() => onChange("alpha")}
        aria-pressed={value === "alpha"}
        className={`${base} ${
          value === "alpha"
            ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
        }`}
      >
        {t("A–Z")}
      </button>
    </div>
  );
}

/** Stable alphabetical sort by a string field (does not mutate the input). */
export function sortAlpha<T>(items: T[], key: (item: T) => string): T[] {
  return [...items].sort((a, b) =>
    key(a).localeCompare(key(b), undefined, { sensitivity: "base" }),
  );
}
