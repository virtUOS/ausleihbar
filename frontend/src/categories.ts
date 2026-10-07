// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Helpers for the admin category tree (#78).

import type { ManageCategory } from "./types";

/** Separator of category path labels ("Kameras › Video"). */
export const PATH_SEPARATOR = " › ";

/** The category tree of the manage list: children per parent (null = top
 *  level) in sibling order (the API lists rows in tree pre-order), and the
 *  rows reachable from a top-level one in pre-order (a live row below a
 *  trashed parent is not). */
export function categoryTree(rows: ManageCategory[]) {
  const childrenOf = new Map<number | null, ManageCategory[]>();
  for (const row of rows) {
    const list = childrenOf.get(row.parent) ?? [];
    list.push(row);
    childrenOf.set(row.parent, list);
  }
  const ordered: ManageCategory[] = [];
  const visit = (parent: number | null) => {
    for (const row of childrenOf.get(parent) ?? []) {
      ordered.push(row);
      visit(row.id);
    }
  };
  visit(null);
  return { childrenOf, ordered };
}

/** Ids of `id` and all categories below it. */
export function subtreeIds(id: number, childrenOf: Map<number | null, ManageCategory[]>): Set<number> {
  const ids = new Set<number>([id]);
  const stack = [id];
  while (stack.length) {
    const current = stack.pop()!;
    for (const child of childrenOf.get(current) ?? []) {
      ids.add(child.id);
      stack.push(child.id);
    }
  }
  return ids;
}
