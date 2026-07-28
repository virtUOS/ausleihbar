// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";

/** A sortable `<th>` for a server-ordered table. `active` is the current
 *  `ordering` value (e.g. "status" or "-status"). Clicking cycles
 *  none -> ascending -> descending -> ascending for this column. */
export function SortableTh({
  field,
  label,
  active,
  onSort,
  className = "",
}: {
  field: string;
  label: string;
  active: string;
  onSort: (next: string) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const isAsc = active === field;
  const isDesc = active === `-${field}`;
  const next = isAsc ? `-${field}` : field;
  const ariaSort = isAsc ? "ascending" : isDesc ? "descending" : "none";
  const Icon = isAsc ? ChevronUp : isDesc ? ChevronDown : ChevronsUpDown;
  return (
    <th className={`px-3 py-2 ${className}`} aria-sort={ariaSort}>
      <button
        type="button"
        onClick={() => onSort(next)}
        aria-label={t("Sort by {{column}}", { column: label })}
        className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-slate-100"
      >
        {label}
        <Icon
          className={`h-3.5 w-3.5 ${
            isAsc || isDesc ? "text-slate-700 dark:text-slate-200" : "text-slate-400 dark:text-slate-500"
          }`}
        />
      </button>
    </th>
  );
}
