// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarPlus } from "lucide-react";
import type { PlaceKind } from "../types";

/** "Book later" as an icon button (calendar): opens the Book page with the
 *  place preselected (another day or time, series). Shown next to the
 *  book-now actions; the label is in `aria-label` and the tooltip. */
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
      title={t("Book later")}
      className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-800 transition-colors duration-150 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800 ${className}`}
    >
      <CalendarPlus aria-hidden className="h-5 w-5" />
    </Link>
  );
}
