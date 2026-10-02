// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useSyncExternalStore } from "react";

/**
 * Lending-area pool scope for admins who are also assigned as lenders
 * ("My pools (n) | All pools"). "mine" (default) lets the backend narrow the
 * lending lists, counters and pool choices to the admin's own pools; "all"
 * sends `X-Pool-Scope: all` with every API request (support view).
 *
 * A view filter only — never a permission: the backend ignores the header for
 * non-admins, so it can't widen a lender's view. Remembered per browser.
 */
export type PoolScope = "mine" | "all";

const STORAGE_KEY = "ausleihbar.manage.poolScope";

function readStored(): PoolScope {
  try {
    return localStorage.getItem(STORAGE_KEY) === "all" ? "all" : "mine";
  } catch {
    return "mine";
  }
}

let current: PoolScope = readStored();
const listeners = new Set<() => void>();

export function getPoolScope(): PoolScope {
  return current;
}

export function setPoolScope(scope: PoolScope): void {
  if (scope === current) return;
  current = scope;
  try {
    if (scope === "all") localStorage.setItem(STORAGE_KEY, "all");
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable — the choice just isn't remembered */
  }
  listeners.forEach((listener) => listener());
}

export function subscribePoolScope(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The current scope; re-renders the caller when it changes. */
export function usePoolScope(): PoolScope {
  return useSyncExternalStore(subscribePoolScope, getPoolScope, getPoolScope);
}

// "Locked" while a page holds unsaved client-side work that a scope switch
// would discard (switching remounts the page): e.g. a walk-in basket.
let locked = false;
const lockListeners = new Set<() => void>();

export function setPoolScopeLocked(next: boolean): void {
  if (next === locked) return;
  locked = next;
  lockListeners.forEach((listener) => listener());
}

function subscribeLock(listener: () => void): () => void {
  lockListeners.add(listener);
  return () => {
    lockListeners.delete(listener);
  };
}

const getLocked = () => locked;

/** Whether the scope switch is currently locked; re-renders on change. */
export function usePoolScopeLocked(): boolean {
  return useSyncExternalStore(subscribeLock, getLocked, getLocked);
}

/** Request header for the active scope (sent only for the support view). */
export function poolScopeHeaders(): Record<string, string> {
  return current === "all" ? { "X-Pool-Scope": "all" } : {};
}
