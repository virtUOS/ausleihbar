// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";

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

  function onDragStart(id: number) {
    dragId.current = id;
  }

  function onDragEnter(id: number) {
    const from = dragId.current;
    if (from === null || from === id) return;
    const fromIndex = order.findIndex((item) => item.id === from);
    const toIndex = order.findIndex((item) => item.id === id);
    if (fromIndex < 0 || toIndex < 0) return;
    const next = order.slice();
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    setOrder(next); // reflect live during drag; persist on drop
  }

  function onDrop() {
    if (dragId.current === null) return;
    dragId.current = null;
    const previous = items;
    persist(order.map((item) => item.id)).catch(() => setOrder(previous));
  }

  return { order, move, onDragStart, onDragEnter, onDrop };
}
