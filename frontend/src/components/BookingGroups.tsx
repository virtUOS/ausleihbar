// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { MapPin, Minus, Plus } from "lucide-react";

import { DeleteButton } from "./RowActions";
import { formatPeriod } from "../manage";
import { poolAccent } from "../poolAccent";
import type { BookingGroup, BookingGroupItem } from "../types";

/** Controls for the cart's quantity stepper + remove. Omit for a read-only
 *  summary (confirmation screen). The `remaining` map is keyed by
 *  `${product}|${start}|${end}` and holds how many more units are still free. */
export interface CartControls {
  onAddMore: (itemId: number) => void;
  onRemoveOne: (itemId: number) => void;
  onRemoveLine: (itemIds: number[]) => void;
  remaining: Record<string, number>;
  busy?: boolean;
}

/** One product collapsed across its individual reserved units (= quantity). */
interface ProductLine {
  product: number;
  title: string;
  image?: string | null;
  ids: number[];
}

function byProduct(items: BookingGroupItem[]): ProductLine[] {
  const lines = new Map<number, ProductLine>();
  const order: number[] = [];
  for (const item of items) {
    let line = lines.get(item.product);
    if (!line) {
      line = { product: item.product, title: item.product_title, image: item.image, ids: [] };
      lines.set(item.product, line);
      order.push(item.product);
    }
    line.ids.push(item.id);
  }
  return order.map((p) => lines.get(p)!);
}

/** Renders a reservation's items grouped by pool, then by period — the
 *  canonical summary used in the cart and the confirmation screen. Pass
 *  `controls` to make it an editable cart (quantity stepper + remove). */
export function BookingGroups({
  groups,
  controls,
}: {
  groups: BookingGroup[];
  controls?: CartControls;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      {groups.map((group) => {
        // Every item in a group shares one pool, so the first one's accent
        // colours the whole group (#16) — a clear visual anchor per pool.
        const accent = poolAccent(group.periods[0]?.items[0]?.accent_color);
        return (
        <div
          key={group.pool_id}
          className="flex overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800"
        >
          {/* Left accent strip: the group's pool colour (#16), the clearest
              visual anchor for "which pool does this belong to". */}
          <div aria-hidden className={`w-1.5 shrink-0 ${accent.bar}`} />
          <div className="min-w-0 flex-1">
          <div className={`flex items-center gap-2 border-b border-slate-100 px-4 py-2.5 dark:border-slate-800 ${accent.tint}`}>
            <MapPin aria-hidden className={`h-4 w-4 shrink-0 ${accent.text}`} />
            <Link
              to={`/pools/${group.pool_id}`}
              className="font-semibold text-slate-900 hover:text-brand-700 hover:underline dark:text-slate-100 dark:hover:text-brand-400"
            >
              {group.pool}
            </Link>
            {group.room && <span className="text-sm text-slate-600 dark:text-slate-300">· {group.room}</span>}
          </div>

          <div className="space-y-3 p-3">
            {group.periods.map((period, idx) => {
              const lines = byProduct(period.items);
              return (
                <div key={idx} className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                  <div className="border-b border-slate-100 px-3 py-2 text-xs font-medium text-slate-600 dark:border-slate-800 dark:text-slate-300">
                    {formatPeriod(period.start, period.end, period.lending_type)}
                  </div>
                  <ul className="divide-y divide-slate-50 dark:divide-slate-800">
                    {lines.map((line) => {
                      const key = `${line.product}|${period.start}|${period.end}`;
                      const qty = line.ids.length;
                      const canAdd = (controls?.remaining[key] ?? 0) > 0;
                      return (
                        <li key={line.product} className="flex items-center gap-3 px-3 py-2.5">
                          <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-slate-100 text-lg dark:bg-slate-800">
                            {line.image ? (
                              <img src={line.image} alt="" className="h-full w-full object-cover" />
                            ) : (
                              <span aria-hidden>📦</span>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                              {line.title}
                            </p>
                            {!controls && qty > 1 && (
                              <p className="text-xs text-slate-600 dark:text-slate-300">× {qty}</p>
                            )}
                          </div>

                          {controls ? (
                            <div className="flex items-center gap-2">
                              <div className="flex items-center gap-1 rounded-full border border-slate-200 p-0.5 dark:border-slate-800">
                                <button
                                  type="button"
                                  disabled={controls.busy || qty <= 1}
                                  onClick={() => controls.onRemoveOne(line.ids[line.ids.length - 1])}
                                  aria-label={t("Remove one")}
                                  title={qty <= 1 ? t("Use the trash button to remove") : undefined}
                                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800"
                                >
                                  <Minus aria-hidden className="h-4 w-4" />
                                </button>
                                <span className="min-w-[1.5rem] text-center text-sm font-semibold text-slate-900 dark:text-slate-100">
                                  {qty}
                                </span>
                                <button
                                  type="button"
                                  disabled={controls.busy || !canAdd}
                                  onClick={() => controls.onAddMore(line.ids[0])}
                                  aria-label={t("Add one more")}
                                  title={!canAdd ? t("No more available in this period") : undefined}
                                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800"
                                >
                                  <Plus aria-hidden className="h-4 w-4" />
                                </button>
                              </div>
                              <DeleteButton
                                onClick={() => controls.onRemoveLine(line.ids)}
                                disabled={controls.busy}
                              />
                            </div>
                          ) : (
                            qty > 1 && (
                              <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                                × {qty}
                              </span>
                            )
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
          </div>
        </div>
        );
      })}
    </div>
  );
}
