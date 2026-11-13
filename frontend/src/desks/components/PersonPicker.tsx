// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { UserPicker, type PickedUser } from "../../components/UserPicker";
import { desksApi } from "../api";
import type { PersonChoice } from "../types";

/** Pick one member of a department by name (>= 3 characters). Shows the chosen
 *  person as a chip with a clear button. The only place people are looked up
 *  by name: fixed owners, "mark absent", "book for". */
export function PersonPicker({
  pool,
  value,
  onChange,
  label,
}: {
  pool: number;
  value: PersonChoice | null;
  onChange: (person: PersonChoice | null) => void;
  label: string;
}) {
  const { t } = useTranslation();
  const search = useCallback(
    (term: string): Promise<PickedUser[]> =>
      desksApi
        .people(pool, term)
        .then((rows) =>
          rows.map((p) => ({ id: p.id, username: p.name, display_name: p.name, email: "" })),
        ),
    [pool],
  );
  if (value) {
    return (
      <div>
        <span className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300">
          {label}
        </span>
        <span className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-slate-100 pl-4 pr-1 text-sm font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100">
          {value.name}
          <button
            type="button"
            aria-label={t("Remove {{name}}", { name: value.name })}
            onClick={() => onChange(null)}
            className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-slate-200 dark:hover:bg-slate-700"
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </span>
      </div>
    );
  }
  return (
    <UserPicker
      label={label}
      placeholder={t("Search by name (min. 3 characters)…")}
      minChars={3}
      search={search}
      onPick={(u) => onChange({ id: u.id, name: u.display_name })}
    />
  );
}
