// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, UserRound } from "lucide-react";
import { PersonPicker } from "../components/PersonPicker";
import type { PersonChoice } from "../types";

/** "Book for another person" (assistants): a collapsed toggle that reveals
 *  the person field. Collapsing it books for oneself again. */
export function ForOtherPerson({
  pool,
  value,
  onChange,
}: {
  pool: number;
  value: PersonChoice | null;
  onChange: (person: PersonChoice | null) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(value !== null);
  const expanded = open || value !== null;
  return (
    <div className="mb-6 max-w-md">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={expanded ? "book-for-other" : undefined}
        onClick={() => {
          if (expanded) onChange(null);
          setOpen(!expanded);
        }}
        className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        <UserRound aria-hidden className="h-4 w-4" />
        {t("Book for another person")}
        <ChevronDown
          aria-hidden
          className={`h-4 w-4 transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
        />
      </button>
      {expanded && (
        <div id="book-for-other" className="mt-3">
          <PersonPicker pool={pool} value={value} onChange={onChange} label={t("Person")} />
          {value && (
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              {t("Free places are shown for {{name}}.", { name: value.name })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
