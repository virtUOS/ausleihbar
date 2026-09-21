// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LayoutGrid, Search } from "lucide-react";
import { useAuth } from "../auth";
import { useOutsideClose } from "../useOutsideClose";
import { useAppFunctions, filterFunctions } from "../appFunctions";

/** Prominent, always-expanded function finder shown in the admin/lending area
 *  header: a labelled search field with a results dropdown, plus a visible link
 *  to the full overview (issue #28). */
export function FunctionSearchBar() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const functions = useAppFunctions();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));

  if (!user?.is_lender && !user?.is_staff) return null;

  const results = filterFunctions(functions, query);

  function go(to: string) {
    setOpen(false);
    setQuery("");
    navigate(to);
  }

  return (
    <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative w-full sm:max-w-sm" ref={ref}>
        <Search
          aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
        />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "Enter" && results[0]) go(results[0].to);
          }}
          aria-label={t("Find a function")}
          placeholder={t("Search functions… (e.g. walk-in, strikes)")}
          className="w-full rounded-full border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 outline-none focus:border-brand-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
        {open && query.trim() && (
          <ul className="absolute z-30 mt-1 max-h-[60vh] w-full overflow-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
            {results.length === 0 && (
              <li className="px-4 py-4 text-center text-sm text-slate-400 dark:text-slate-400">
                {t("No matching function.")}
              </li>
            )}
            {results.map((fn) => (
              <li key={fn.to}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => go(fn.to)}
                  className="flex w-full flex-col items-start px-4 py-2 text-left hover:bg-slate-100 dark:hover:bg-slate-700"
                >
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {fn.label}
                    <span className="ml-2 text-xs font-normal text-slate-400 dark:text-slate-400">
                      {fn.group}
                    </span>
                  </span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {fn.description}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Link
        to="/functions"
        className="inline-flex shrink-0 items-center gap-1.5 self-start text-sm font-medium text-slate-600 underline-offset-2 hover:underline dark:text-slate-300 sm:self-auto"
      >
        <LayoutGrid aria-hidden className="h-4 w-4" />
        {t("All functions")}
      </Link>
    </div>
  );
}
