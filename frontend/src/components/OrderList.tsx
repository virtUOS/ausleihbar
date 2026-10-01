// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { ReorderControls } from "./ReorderControls";

/** A reorderable list (↑/↓) for the manual display order of selected ids.
 *  Hidden until there is more than one entry to arrange. Used by the section
 *  editor (product types, sets) and the product-type editor (products). */
export function OrderList({
  label,
  ids,
  labelFor,
  onMove,
}: {
  label: string;
  ids: number[];
  labelFor: (id: number) => string;
  onMove: (id: number, delta: number) => void;
}) {
  if (ids.length < 2) return null;
  return (
    <div className="mt-2">
      <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{label}</p>
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
        {ids.map((id, index) => (
          <li key={id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
            <span className="min-w-0 truncate text-slate-800 dark:text-slate-100">
              {labelFor(id)}
            </span>
            <ReorderControls
              label={labelFor(id)}
              isFirst={index === 0}
              isLast={index === ids.length - 1}
              onUp={() => onMove(id, -1)}
              onDown={() => onMove(id, 1)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Move `id` by `delta` (-1 up / +1 down) within `ids`; returns `ids` unchanged
 *  when the move is out of range. */
export function moveId(ids: number[], id: number, delta: number): number[] {
  const from = ids.indexOf(id);
  const to = from + delta;
  if (from === -1 || to < 0 || to >= ids.length) return ids;
  const next = [...ids];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
}
