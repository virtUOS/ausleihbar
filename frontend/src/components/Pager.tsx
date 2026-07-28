// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { PAGE_SIZE } from "../usePagedList";

/** The slice of a usePagedList() instance the pager needs. */
export interface PagedLike {
  page: number;
  count: number;
  hasPrev: boolean;
  hasNext: boolean;
  setPage: (page: number) => void;
}

/**
 * Pager for admin list pages — sits *below* the table. Shows the "from–to of
 * count" summary and (when there is more than one page) prev/next controls plus
 * an editable page field. Renders nothing for an empty list. Wire it to a
 * usePagedList() instance: `<Pager list={products} />`.
 */
export function Pager({ list }: { list: PagedLike }) {
  const { t } = useTranslation();
  const { page, count, hasPrev, hasNext, setPage } = list;
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const [pageInput, setPageInput] = useState(String(page));
  useEffect(() => setPageInput(String(page)), [page]);

  if (count === 0) return null;

  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, count);

  function commit() {
    const v = parseInt(pageInput, 10);
    if (Number.isNaN(v)) {
      setPageInput(String(page));
      return;
    }
    setPage(Math.min(Math.max(1, v), totalPages));
  }

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500 dark:text-slate-400">
      <span>{t("{{from}}–{{to}} of {{count}}", { from, to, count })}</span>
      {totalPages > 1 && (
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={!hasPrev}
            onClick={() => setPage(page - 1)}
            aria-label={t("Previous page")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-300 text-slate-600 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-30 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </button>
          <span className="flex items-center gap-1 text-slate-600 dark:text-slate-300">
            {t("Page")}
            <input
              type="number"
              min={1}
              max={totalPages}
              value={pageInput}
              onChange={(e) => setPageInput(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commit();
                }
              }}
              aria-label={t("Go to page")}
              className="w-12 rounded-md border border-slate-300 px-1 py-1 text-center text-slate-900 focus:border-slate-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-500"
            />
            / {totalPages}
          </span>
          <button
            type="button"
            disabled={!hasNext}
            onClick={() => setPage(page + 1)}
            aria-label={t("Next page")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-300 text-slate-600 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-30 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ChevronRight aria-hidden className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
