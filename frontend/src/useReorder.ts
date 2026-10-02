// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";

/** Returns a copy of `list` with the item at `fromIndex` moved to `toIndex`. */
export function moveBefore<T>(list: T[], fromIndex: number, toIndex: number): T[] {
  const next = list.slice();
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

/** Marks a native drag as a "move" (Firefox won't start a drag without data). */
export function startDrag(e: { dataTransfer?: DataTransfer | null }, id: number) {
  if (!e.dataTransfer) return;
  e.dataTransfer.setData("application/x-ausleihbar-id", String(id));
  e.dataTransfer.effectAllowed = "move";
}

/**
 * Local drag-and-drop / arrow reordering for an admin table.
 *
 * Holds a working copy of `items`, exposes `move` (arrow buttons) and HTML5
 * drag handlers, and persists the new id order via `persist`. On a failed
 * save the local order reverts to the last known server order.
 */
export function useReorder<T extends { id: number }>(
  items: T[],
  persist: (ids: number[]) => Promise<unknown>,
) {
  const [order, setOrder] = useState<T[]>(items);
  const dragId = useRef<number | null>(null);
  // Order when the current drag started — restored if the drag is abandoned.
  const dragStartOrder = useRef<T[]>(items);

  // Resync only when the *set* of items changes (add / delete / refetch),
  // not on every parent render — otherwise an in-progress drag would reset.
  const signature = items.map((item) => item.id).join(",");
  useEffect(() => {
    setOrder(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  function save(next: T[]) {
    const previous = order;
    setOrder(next);
    persist(next.map((item) => item.id)).catch(() => setOrder(previous));
  }

  function move(id: number, direction: -1 | 1) {
    const index = order.findIndex((item) => item.id === id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= order.length) return;
    const next = order.slice();
    [next[index], next[target]] = [next[target], next[index]];
    save(next);
  }

  function onDragStart(id: number, e?: { dataTransfer?: DataTransfer | null }) {
    if (e) startDrag(e, id);
    dragId.current = id;
    dragStartOrder.current = order;
  }

  function onDragEnter(id: number) {
    const from = dragId.current;
    if (from === null || from === id) return;
    const fromIndex = order.findIndex((item) => item.id === from);
    const toIndex = order.findIndex((item) => item.id === id);
    if (fromIndex < 0 || toIndex < 0) return;
    const next = moveBefore(order, fromIndex, toIndex);
    setOrder(next); // reflect live during drag; persist on drop
  }

  function onDrop() {
    if (dragId.current === null) return;
    dragId.current = null;
    const previous = items;
    persist(order.map((item) => item.id)).catch(() => setOrder(previous));
  }

  // Fires after drop too (drop runs first and clears dragId); a drag that ended
  // without a drop is abandoned: discard the live preview.
  function onDragEnd() {
    if (dragId.current === null) return;
    dragId.current = null;
    setOrder(dragStartOrder.current);
  }

  return { order, move, onDragStart, onDragEnter, onDrop, onDragEnd };
}
