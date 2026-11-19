// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface AccessGroupOption {
  id: number;
  name: string;
  /** Already a group of the department itself: listed first. */
  in_pool?: boolean;
}

const hintCls = "text-xs text-slate-600 dark:text-slate-300";

/**
 * A checkbox list of access groups (44px rows, the department's own groups
 * first). `groups` null shows a loading line. Used for the "Who may book"
 * pickers of rooms, places and the bulk groups dialog.
 */
export function AccessGroupCheckboxes({
  groups,
  selected,
  onToggle,
  disabledIds = [],
  disabled = false,
  legend,
  hint,
  before,
  bordered = false,
}: {
  groups: AccessGroupOption[] | null;
  selected: number[];
  onToggle: (id: number) => void;
  /** Single groups that can't be toggled (e.g. chosen in the other list). */
  disabledIds?: number[];
  /** The whole list is read-only (e.g. it follows the room). */
  disabled?: boolean;
  legend: ReactNode;
  hint?: ReactNode;
  /** Rendered between hint and list (e.g. a "Like the room" switch). */
  before?: ReactNode;
  /** Frame the list (several lists in one form). */
  bordered?: boolean;
}) {
  const { t } = useTranslation();
  const sorted = groups
    ? [...groups].sort((a, b) => Number(b.in_pool ?? false) - Number(a.in_pool ?? false))
    : null;
  return (
    <fieldset>
      <legend className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300">
        {legend}
      </legend>
      {hint && <p className={`mb-1 ${hintCls}`}>{hint}</p>}
      {before}
      {sorted === null ? (
        <p className={hintCls}>{t("Loading…")}</p>
      ) : sorted.length === 0 ? (
        <p className={hintCls}>{t("No access groups defined yet.")}</p>
      ) : (
        <div
          className={`flex max-h-48 flex-col overflow-y-auto${
            bordered ? " rounded-lg border border-slate-200 px-2 dark:border-slate-700" : ""
          }`}
        >
          {sorted.map((g) => (
            <label
              key={g.id}
              className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200"
            >
              <input
                type="checkbox"
                className="h-5 w-5"
                checked={selected.includes(g.id)}
                disabled={disabled || disabledIds.includes(g.id)}
                onChange={() => onToggle(g.id)}
              />
              <span>{g.name}</span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
