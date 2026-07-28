// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { Booking } from "./types";

interface CartContextValue {
  cart: Booking | null;
  count: number;
  refresh: () => Promise<void>;
  add: (product: number, start: string, end: string) => Promise<void>;
  addSet: (set: number, start: string, end: string) => Promise<void>;
  duplicate: (itemId: number) => Promise<void>;
  remove: (itemId: number) => Promise<void>;
  submit: (note: string) => Promise<Booking>;
  clear: () => Promise<void>;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [cart, setCart] = useState<Booking | null>(null);

  // Serialize all cart reads/writes. Each call returns a fully-hydrated cart;
  // running them one-at-a-time stops a slower earlier response from clobbering
  // a newer one (the "added items don't all show up until reload" race).
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const runExclusive = useCallback(<T,>(op: () => Promise<T>): Promise<T> => {
    const run = queue.current.then(op, op);
    // Keep the chain alive even if an op rejects, so one failure doesn't wedge it.
    queue.current = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }, []);

  const refresh = useCallback(async () => {
    if (!user?.authenticated) {
      setCart(null);
      return;
    }
    await runExclusive(async () => {
      try {
        const { cart } = await api.getCart();
        setCart(cart);
      } catch {
        setCart(null);
      }
    });
  }, [user?.authenticated, runExclusive]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const add = useCallback(
    (product: number, start: string, end: string) =>
      runExclusive(async () => {
        setCart(await api.addToCart(product, start, end));
      }),
    [runExclusive],
  );

  const addSet = useCallback(
    (set: number, start: string, end: string) =>
      runExclusive(async () => {
        setCart(await api.addSetToCart(set, start, end));
      }),
    [runExclusive],
  );

  const duplicate = useCallback(
    (itemId: number) =>
      runExclusive(async () => {
        setCart(await api.duplicateCartItem(itemId));
      }),
    [runExclusive],
  );

  const remove = useCallback(
    (itemId: number) =>
      runExclusive(async () => {
        setCart(await api.removeCartItem(itemId));
      }),
    [runExclusive],
  );

  const submit = useCallback(
    (note: string) =>
      runExclusive(async () => {
        const booking = await api.submitCart(note);
        setCart(null);
        return booking;
      }),
    [runExclusive],
  );

  const clear = useCallback(
    () =>
      runExclusive(async () => {
        await api.clearCart();
        setCart(null);
      }),
    [runExclusive],
  );

  const count = cart?.items.length ?? 0;

  return (
    <CartContext.Provider
      value={{ cart, count, refresh, add, addSet, duplicate, remove, submit, clear }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within a CartProvider");
  return ctx;
}
