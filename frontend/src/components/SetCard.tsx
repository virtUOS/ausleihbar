// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronDown, Layers } from "lucide-react";
import type { Crumb } from "./Breadcrumbs";
import type { SetBrief } from "../types";

/**
 * A set as a card (#93): visibly different from a product row — honey-tinted
 * surface, a "Set" badge and a second card edge peeking out below (stacked
 * look). The title is a stretched link to the set page; the "Show contents"
 * toggle sits above that link (no nested interactive elements) and expands
 * the item list ("2 × Stativ") in place. In dark mode the main surface stays
 * opaque (the stack edge must not shine through) with a honey tint layered
 * on top as a flat gradient.
 */
export function SetCard({ set, crumbs }: { set: SetBrief; crumbs?: Crumb[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <div className="group relative pb-1.5">
      {/* The second card edge of the stack. */}
      <div
        aria-hidden
        className="absolute inset-x-3 bottom-0 top-3 rounded-2xl border border-brand-200 bg-brand-100 transition-transform duration-200 ease-out-quart group-hover:translate-y-0.5 dark:border-brand-900/60 dark:bg-brand-900/30"
      />
      <div className="relative rounded-2xl border border-brand-200 bg-brand-50 p-3 transition-all duration-200 ease-out-quart group-hover:-translate-y-0.5 group-hover:border-brand-400 group-hover:shadow-md group-hover:shadow-slate-900/[0.04] dark:border-brand-900/60 dark:bg-slate-900 dark:bg-gradient-to-b dark:from-brand-900/25 dark:to-brand-900/25 dark:group-hover:border-brand-500">
        <div className="flex items-start gap-3">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white text-2xl dark:bg-slate-800">
            {set.image ? (
              <img src={set.image} alt="" className="h-full w-full object-cover" />
            ) : (
              <span aria-hidden>🎒</span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-200 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-slate-900">
              <Layers aria-hidden className="h-3 w-3" />
              {t("Set")}
            </span>
            <p className="mt-1 font-bold text-slate-900 dark:text-slate-100">
              {/* Stretched link: the whole card (but the toggle) opens the set. */}
              <Link
                to={`/sets/${set.id}`}
                state={crumbs ? { crumbs } : undefined}
                className="rounded after:absolute after:inset-0 after:rounded-2xl after:content-[''] hover:text-brand-800 dark:hover:text-brand-300"
              >
                {set.name}
              </Link>
            </p>
            <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("{{count}} item", { count: set.item_count })}
            </p>
            {set.description_text && (
              <p className="mt-1 line-clamp-2 text-xs text-slate-600 dark:text-slate-300">
                {set.description_text}
              </p>
            )}
          </div>
        </div>
        {set.items.length > 0 && (
          <>
            <button
              type="button"
              aria-expanded={open}
              aria-controls={listId}
              aria-label={
                open
                  ? t("Hide contents of {{name}}", { name: set.name })
                  : t("Show contents of {{name}}", { name: set.name })
              }
              onClick={() => setOpen((o) => !o)}
              className="relative z-10 mt-2 inline-flex min-h-10 items-center gap-1 rounded-full px-3 text-sm font-medium text-brand-800 transition-colors duration-150 hover:bg-brand-100 dark:text-brand-300 dark:hover:bg-brand-900/30"
            >
              {open ? t("Hide contents") : t("Show contents")}
              <ChevronDown
                aria-hidden
                className={`h-4 w-4 transition-transform duration-150 ease-out-quart ${open ? "rotate-180" : ""}`}
              />
            </button>
            <ul
              id={listId}
              hidden={!open}
              className="relative z-10 mt-1 space-y-0.5 border-t border-brand-200 px-3 pt-2 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-200"
            >
              {set.items.map(({ product, quantity }) => (
                <li key={product.id}>
                  <span className="tabular-nums text-slate-600 dark:text-slate-300">
                    {t("{{quantity}} ×", { quantity })}
                  </span>{" "}
                  {product.title}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

/** Set cards as a grid, with an optional sub-heading (when products follow). */
export function SetCardGrid({
  sets,
  crumbs,
  headingLevel,
}: {
  sets: SetBrief[];
  crumbs?: Crumb[];
  /** Renders a "Sets" sub-heading at this level; omitted = no heading. */
  headingLevel?: 3 | 4 | 5;
}) {
  const { t } = useTranslation();
  if (sets.length === 0) return null;
  const Heading = headingLevel ? (`h${headingLevel}` as const) : null;
  return (
    <div className="mb-3">
      {Heading && (
        <Heading className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
          <Layers aria-hidden className="h-3.5 w-3.5" />
          {t("Sets")}
        </Heading>
      )}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {sets.map((set) => (
          <SetCard key={set.id} set={set} crumbs={crumbs} />
        ))}
      </div>
    </div>
  );
}
