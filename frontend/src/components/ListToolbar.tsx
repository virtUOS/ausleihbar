// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

/**
 * Search box for admin list pages — sits *above* the table. Wire it to a
 * usePagedList() instance. The pager lives in a separate `<Pager>` below the
 * table; for fully-loaded lists that only filter client-side (e.g. reorderable
 * lists, `hidePager`), pass `count` to show a plain entry total here instead.
 */
export function ListToolbar({
  search,
  onSearch,
  count,
  placeholder,
  hidePager = false,
}: {
  search: string;
  onSearch: (value: string) => void;
  count?: number;
  placeholder?: string;
  hidePager?: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <input
        type="search"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder={placeholder ?? t("Search…")}
        className="w-full max-w-xs rounded-full border border-slate-300 bg-slate-50 px-4 py-1.5 text-sm placeholder:text-slate-400 focus:border-slate-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-200 dark:placeholder:text-slate-500 dark:focus:border-slate-500"
      />
      {hidePager && count !== undefined && (
        <span className="text-sm text-slate-500 dark:text-slate-400">
          {count === 0 ? t("No entries") : t("{{count}} entries", { count })}
        </span>
      )}
    </div>
  );
}
