// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useCart } from "../cart";
import { useConfirm } from "../components/ConfirmDialog";
import { BookingGroups, type CartControls } from "../components/BookingGroups";
import type { Booking } from "../types";

export function CartPage() {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const { cart, duplicate, remove, submit, clear } = useCart();
  const confirm = useConfirm();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<Booking | null>(null);
  const [remaining, setRemaining] = useState<Record<string, number>>({});

  // Distinct (product, period) lines in the cart — drives the availability
  // lookup that gates the quantity "+" button.
  const lines = useMemo(() => {
    const out: { product: number; start: string | null; end: string | null }[] = [];
    const seen = new Set<string>();
    cart?.groups.forEach((g) =>
      g.periods.forEach((p) => {
        new Set(p.items.map((i) => i.product)).forEach((product) => {
          const key = `${product}|${p.start}|${p.end}`;
          if (!seen.has(key)) {
            seen.add(key);
            out.push({ product, start: p.start, end: p.end });
          }
        });
      }),
    );
    return out;
  }, [cart]);

  // How many more units of each line are still free (excludes what's held).
  useEffect(() => {
    let cancelled = false;
    if (lines.length === 0) {
      setRemaining({});
      return;
    }
    Promise.all(
      lines.map(async (l) => {
        const key = `${l.product}|${l.start}|${l.end}`;
        try {
          const a = await api.getAvailability(l.product, l.start!, l.end!);
          return [key, a.available] as const;
        } catch {
          return [key, 0] as const;
        }
      }),
    ).then((entries) => {
      if (!cancelled) setRemaining(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [lines]);

  if (!user?.authenticated) {
    return (
      <div className="py-10 text-center">
        <p className="mb-3 text-slate-600 dark:text-slate-300">{t("Please sign in to use the cart.")}</p>
        <button
          onClick={login}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
        >
          {t("Sign in")}
        </button>
      </div>
    );
  }

  if (submitted) {
    return (
      <div>
        <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Booking submitted")}</h1>
        <div className="mb-4 rounded-xl border border-green-200 bg-green-50 p-4 text-sm dark:border-green-900/50 dark:bg-green-950/40">
          <p className="text-green-800 dark:text-green-300">
            {t("Your booking number is")}{" "}
            <span className="font-semibold">{submitted.code}</span>.{" "}
            {t("The staff will confirm it. You can track it under")}{" "}
            <Link to="/bookings" className="font-medium underline">{t("My bookings")}</Link>.
          </p>
        </div>
        <BookingGroups groups={submitted.groups} />
        {submitted.note && (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{t("Message: {{note}}", { note: submitted.note })}</p>
        )}
      </div>
    );
  }

  const isEmpty = !cart || cart.items.length === 0;

  async function act(fn: () => Promise<void>) {
    setActing(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Could not update the cart."));
    } finally {
      setActing(false);
    }
  }

  const controls: CartControls = {
    onAddMore: (id) => act(() => duplicate(id)),
    onRemoveOne: (id) => act(() => remove(id)),
    onRemoveLine: async (ids) => {
      if (
        !(await confirm({
          message: t("Remove this item from the cart?"),
          confirmLabel: t("Remove"),
          danger: true,
        }))
      )
        return;
      await act(async () => {
        for (const id of ids) await remove(id);
      });
    },
    remaining,
    busy: acting,
  };

  const noteRequired = cart?.note_required ?? false;

  async function doSubmit() {
    if (noteRequired && !note.trim()) {
      setError(t("Please add a message to the lending team to submit this order."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setSubmitted(await submit(note.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Could not submit the booking."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold text-slate-900 dark:text-slate-100">{t("Cart")}</h1>
      {cart?.code && (
        <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
          {t("Booking number")} <span className="font-medium">{cart.code}</span>
          {cart.expires_at && (
            <> · {t("held until {{time}}", { time: new Date(cart.expires_at).toLocaleTimeString() })}</>
          )}
        </p>
      )}

      {isEmpty ? (
        <div className="py-10 text-center text-slate-500 dark:text-slate-400">
          <p className="mb-3">{t("Your cart is empty.")}</p>
          <Link to="/" className="font-medium text-slate-700 underline dark:text-slate-200">
            {t("Browse the catalog")}
          </Link>
        </div>
      ) : (
        <>
          <BookingGroups groups={cart!.groups} controls={controls} />

          <div className="mt-5">
            <label htmlFor="cart-note" className="text-sm font-medium text-slate-700 dark:text-slate-200">
              {noteRequired ? t("Message to the staff (required)") : t("Message to the staff (optional)")}
              {noteRequired && <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>}
            </label>
            {noteRequired && (
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {t("One of the pools in your order asks for a message before it can be submitted.")}
              </p>
            )}
            <textarea
              id="cart-note"
              rows={3}
              required={noteRequired}
              aria-required={noteRequired}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("e.g. needed for the music seminar; picked up by Alex Müller")}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
            />
          </div>

          {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={doSubmit}
              disabled={busy}
              className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
            >
              {busy ? t("Submitting…") : t("Submit booking")}
            </button>
            <button
              type="button"
              onClick={() => clear()}
              disabled={busy}
              className="rounded-full border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {t("Discard cart")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
