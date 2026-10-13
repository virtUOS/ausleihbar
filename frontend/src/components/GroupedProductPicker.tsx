// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ProductGroupRef } from "../types";

export type { ProductGroupRef };

const OTHER_KEY = "__other__";

/** Above this many products the groups start collapsed (search still opens them). */
const COLLAPSE_ABOVE = 12;

function compareOrder(a: number[], b: number[]): number {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

interface Section<P> {
  key: string;
  label: string;
  order: number[];
  items: P[];
}

/** Product list grouped by "Sparte › Kategorie", collapsible, with search. */
export function GroupedProductPicker<
  P extends { id: number; title: string; groups: ProductGroupRef[] },
>({
  products,
  query,
  onQueryChange,
  onPick,
  renderMeta,
  placeholder,
}: {
  products: P[];
  query: string;
  onQueryChange: (q: string) => void;
  onPick: (product: P) => void;
  /** Extra info right of the title (e.g. "daily", limits). */
  renderMeta?: (product: P) => ReactNode;
  placeholder: string;
}) {
  const { t } = useTranslation();
  const baseId = useId();
  // Per-group choice; groups without one follow the default for the list size.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const collapsedByDefault = products.length > COLLAPSE_ABOVE;

  const searching = query.trim() !== "";

  const sections = useMemo(() => {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matching = terms.length
      ? products.filter((p) => {
          const title = p.title.toLowerCase();
          return terms.every((term) => title.includes(term));
        })
      : products;
    const byKey = new Map<string, Section<P>>();
    const other: P[] = [];
    for (const p of matching) {
      if (p.groups.length === 0) {
        other.push(p);
        continue;
      }
      for (const g of p.groups) {
        let sec = byKey.get(g.key);
        if (!sec) {
          sec = { key: g.key, label: g.label, order: g.order, items: [] };
          byKey.set(g.key, sec);
        }
        sec.items.push(p);
      }
    }
    const byTitle = (a: P, b: P) => a.title.localeCompare(b.title);
    const result = [...byKey.values()].sort((a, b) => compareOrder(a.order, b.order));
    result.forEach((s) => s.items.sort(byTitle));
    if (other.length > 0) {
      result.push({ key: OTHER_KEY, label: t("Other"), order: [], items: other.sort(byTitle) });
    }
    return result;
  }, [products, query, t]);

  return (
    <div>
      <input
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="block w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-sm text-slate-900 dark:text-slate-100 dark:bg-slate-800"
      />
      <div className="mt-1 max-h-72 overflow-auto rounded-lg border border-slate-200 dark:border-slate-800">
        {sections.length === 0 && (
          <p className="px-3 py-2 text-sm text-slate-400 dark:text-slate-300">
            {t("No matching products.")}
          </p>
        )}
        {sections.map((sec) => {
          const open = searching || !(collapsed[sec.key] ?? collapsedByDefault);
          const listId = `${baseId}-${sec.key}`;
          const Chevron = open ? ChevronDown : ChevronRight;
          return (
            <section
              key={sec.key}
              className="border-b border-slate-100 last:border-b-0 dark:border-slate-800"
            >
              <h4 className="m-0">
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={listId}
                  disabled={searching}
                  onClick={() => setCollapsed((c) => ({ ...c, [sec.key]: open }))}
                  className="flex w-full items-center gap-1.5 bg-slate-50 px-3 py-1.5 text-left text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:bg-slate-800/50 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  <Chevron aria-hidden className="h-3.5 w-3.5 shrink-0" />
                  <span className="flex-1">{sec.label}</span>
                  <span className="font-normal text-slate-400 dark:text-slate-300">
                    ({sec.items.length})
                  </span>
                </button>
              </h4>
              <ul
                id={listId}
                hidden={!open}
                className="divide-y divide-slate-100 dark:divide-slate-800"
              >
                {sec.items.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => onPick(p)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      <span className="font-medium text-slate-900 dark:text-slate-100">
                        {p.title}
                      </span>
                      {renderMeta && (
                        <span className="text-xs text-slate-400 dark:text-slate-300">
                          {renderMeta(p)}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
