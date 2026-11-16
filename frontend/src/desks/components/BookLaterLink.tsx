// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarPlus } from "lucide-react";
import type { PlaceKind } from "../types";

/** "Book later": opens the Book page with the place preselected (another
 *  day or time, series). Shown next to the book-now actions; the calendar
 *  icon marks it as booking ahead. */
export function BookLaterLink({
  pool,
  place,
  className = "",
}: {
  pool: number;
  place: { id: number; name: string; kind: PlaceKind };
  className?: string;
}) {
  const { t } = useTranslation();
  const q = new URLSearchParams({ pool: String(pool), place: String(place.id), kind: place.kind });
  return (
    <Link
      to={`/desks/book?${q}`}
      aria-label={t("Book {{name}} for later", { name: place.name })}
      className={`inline-flex min-h-[44px] shrink-0 items-center gap-2 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 transition-colors duration-150 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800 ${className}`}
    >
      <CalendarPlus aria-hidden className="h-4 w-4" />
      {t("Book later")}
    </Link>
  );
}
