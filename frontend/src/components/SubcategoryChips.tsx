// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { CategoryFilterChild } from "../types";

interface SubcategoryChipsProps {
  /** Direct subcategories in sibling order. */
  items: Pick<CategoryFilterChild, "id" | "name" | "product_count">[];
  /** Product count of the unfiltered list ("All"). */
  total: number;
  /** Selected subcategory id, `null` = all. */
  selected: number | null;
  onSelect: (id: number | null) => void;
  /** Accessible name of the chip group. */
  label: string;
  /** Size of the filtered list, announced politely after a chip change. */
  shownCount?: number;
  /** Router state for the "To category" link of the active chip (e.g. the
   *  breadcrumb trail); the link appears whenever a chip is active. */
  linkState?: unknown;
}

/**
 * Filter chips "All (n) | Sub A (n) | …" that narrow a product list to one
 * subcategory's subtree. Pill buttons with `aria-pressed`; wraps on narrow
 * screens. When a chip is active, a "To category <name> ›" link opens that
 * subcategory. Used in the section page's category boxes and on category pages.
 */
export function SubcategoryChips({
  items,
  total,
  selected,
  onSelect,
  label,
  shownCount,
  linkState,
}: SubcategoryChipsProps) {
  const { t } = useTranslation();
  // Only announce after the user changed the filter, not on page load.
  const [touched, setTouched] = useState(false);
  const active = items.find((c) => c.id === selected);
  const chip = (key: string, on: boolean, name: string, count: number, id: number | null) => (
    <button
      key={key}
      type="button"
      aria-pressed={on}
      onClick={() => {
        setTouched(true);
        onSelect(id);
      }}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
        on
          ? "border-brand-500 bg-brand-100 font-semibold text-slate-900 dark:bg-brand-200 dark:text-slate-900"
          : "border-slate-200 text-slate-700 hover:border-brand-400 hover:bg-brand-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-brand-900/30"
      }`}
    >
      {name}
      <span
        className={`text-xs font-semibold ${
          on ? "text-slate-700" : "text-slate-400 dark:text-slate-300"
        }`}
      >
        {count}
      </span>
    </button>
  );
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
      <div role="group" aria-label={label} className="flex flex-wrap gap-1.5">
        {chip("all", active === undefined, t("All"), total, null)}
        {items.map((c) => chip(String(c.id), active?.id === c.id, c.name, c.product_count, c.id))}
      </div>
      {active && (
        <Link
          to={`/categories/${active.id}`}
          state={linkState}
          className="inline-flex items-center gap-0.5 text-sm font-medium text-brand-700 hover:underline dark:text-brand-300"
        >
          {t("To category {{name}}", { name: active.name })}
          <ChevronRight aria-hidden className="h-4 w-4 shrink-0" />
        </Link>
      )}
      {shownCount !== undefined && (
        <p role="status" aria-live="polite" className="sr-only">
          {touched ? t("{{count}} product", { count: shownCount }) : ""}
        </p>
      )}
    </div>
  );
}
