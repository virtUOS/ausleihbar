// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

/** One breadcrumb. A crumb with `to` is a link; the last crumb is the current page. */
export interface Crumb {
  label: string;
  to?: string;
}

/**
 * The parent trail carried in router state. Each shop link passes the trail it
 * wants the next page to show via `state={{ crumbs }}`; pages read it here and
 * append their own crumb. Arriving without state (deep link, search) falls back
 * to just Home / {entity}.
 */
export function useParentCrumbs(): Crumb[] {
  const location = useLocation();
  const state = location.state as { crumbs?: Crumb[] } | null;
  return state?.crumbs ?? [];
}

/**
 * Shop breadcrumb trail. Always starts at Home; `items` are the crumbs after it
 * (parent links + the current page as the last, link-less item).
 */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation();
  const all: Crumb[] = [{ label: t("Home"), to: "/" }, ...items];
  return (
    <nav aria-label={t("Breadcrumb")} className="mb-3">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
        {all.map((crumb, i) => {
          const last = i === all.length - 1;
          return (
            <li key={i} className="flex items-center gap-1">
              {crumb.to && !last ? (
                <Link to={crumb.to} className="hover:underline">
                  {crumb.label}
                </Link>
              ) : (
                <span
                  className={last ? "font-medium text-slate-700 dark:text-slate-200" : undefined}
                  aria-current={last ? "page" : undefined}
                >
                  {crumb.label}
                </span>
              )}
              {!last && (
                <span aria-hidden className="text-slate-300 dark:text-slate-600">
                  ›
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
