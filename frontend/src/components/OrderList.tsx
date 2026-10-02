// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useRef, useState } from "react";

import { ReorderControls } from "./ReorderControls";

/** A reorderable list (↑/↓) for the manual display order of selected ids.
 *  Hidden until there is more than one entry to arrange. Used by the section
 *  editor (product types, sets) and the product-type editor (products). */
export function OrderList({
  label,
  ids,
  labelFor,
  onMove,
  onReorder,
}: {
  label: string;
  ids: number[];
  labelFor: (id: number) => string;
  onMove: (id: number, delta: number) => void;
  /** Receives the full new order after a drag-and-drop. Drag is enabled only when set. */
  onReorder?: (ids: number[]) => void;
}) {
  // Working order shown while dragging (live feedback); null when idle.
  const [dragOrder, setDragOrder] = useState<number[] | null>(null);
  const dragId = useRef<number | null>(null);
  const draggable = !!onReorder;
  const shown = dragOrder ?? ids;

  function onDragEnter(id: number) {
    const from = dragId.current;
    if (from === null || from === id) return;
    const current = dragOrder ?? ids;
    const fromIndex = current.indexOf(from);
    const toIndex = current.indexOf(id);
    if (fromIndex < 0 || toIndex < 0) return;
    const next = current.slice();
    next.splice(fromIndex, 1);
    next.splice(toIndex, 0, from);
    setDragOrder(next);
  }

  function onDrop() {
    const next = dragOrder;
    dragId.current = null;
    setDragOrder(null);
    if (next && next.join(",") !== ids.join(",")) onReorder?.(next);
  }

  function onDragEnd() {
    dragId.current = null;
    setDragOrder(null);
  }

  if (ids.length < 2) return null;
  return (
    <div className="mt-2">
      <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{label}</p>
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
        {shown.map((id, index) => (
          <li
            key={id}
            draggable={draggable}
            onDragStart={draggable ? () => (dragId.current = id) : undefined}
            onDragEnter={draggable ? () => onDragEnter(id) : undefined}
            onDragOver={draggable ? (e) => e.preventDefault() : undefined}
            onDrop={draggable ? onDrop : undefined}
            onDragEnd={draggable ? onDragEnd : undefined}
            className={`flex items-center justify-between gap-2 px-3 py-2 text-sm ${
              draggable ? "cursor-grab bg-white dark:bg-slate-900" : ""
            } ${dragId.current === id && dragOrder ? "bg-brand-50 dark:bg-slate-800" : ""}`}
          >
            <span className="min-w-0 truncate text-slate-800 dark:text-slate-100">
              {labelFor(id)}
            </span>
            <ReorderControls
              label={labelFor(id)}
              isFirst={index === 0}
              isLast={index === shown.length - 1}
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
