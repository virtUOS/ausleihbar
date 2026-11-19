// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

/**
 * The department ("Bereich") of a room or place as a small pill: its name,
 * "ohne Bereich" when unassigned, plus an optional qualifier — "gemischt" on
 * a room whose places belong to several departments, "abweichend" on a place
 * whose department deliberately differs from its room's.
 */
export function DepartmentBadge({
  pool,
  names,
  note,
}: {
  pool: number | null;
  /** Department names by pool id; unknown ids read "Anderer Bereich". */
  names: Map<number, string>;
  note?: "mixed" | "overridden";
}) {
  const { t } = useTranslation();
  const name = pool === null ? t("without department") : (names.get(pool) ?? t("Other department"));
  const qualifier = note === "mixed" ? t("mixed") : note === "overridden" ? t("differs") : null;
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
        pool === null
          ? "border-dashed border-slate-400 text-slate-600 dark:border-slate-500 dark:text-slate-300"
          : "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
      }`}
    >
      <span className="truncate">{name}</span>
      {qualifier && (
        <span className="shrink-0 font-semibold text-amber-800 dark:text-amber-300">· {qualifier}</span>
      )}
    </span>
  );
}
