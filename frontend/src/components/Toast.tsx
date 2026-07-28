// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { createContext, useCallback, useContext, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, TriangleAlert, X } from "lucide-react";

type Variant = "success" | "error";

interface ToastOptions {
  /** Optional action link (e.g. "Go to cart"). */
  to?: string;
  actionLabel?: string;
}

interface ToastItem extends ToastOptions {
  id: number;
  variant: Variant;
  message: string;
}

interface ToastContextValue {
  show: (variant: Variant, message: string, opts?: ToastOptions) => void;
  success: (message: string, opts?: ToastOptions) => void;
  error: (message: string, opts?: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 5000;

/**
 * Lightweight toast stack — brief, clearly-styled confirmations (e.g. after
 * adding to the cart) that don't disable controls or block the page. Mount once
 * near the app root; trigger with `useToast()`.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((toast) => toast.id !== id));
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  // (Re)start the auto-dismiss countdown. Paused while the toast is hovered or
  // focused, so there's time to read it and reach its action — important for
  // keyboard and screen-reader users.
  const arm = useCallback(
    (id: number) => {
      const existing = timers.current.get(id);
      if (existing) clearTimeout(existing);
      timers.current.set(id, setTimeout(() => dismiss(id), AUTO_DISMISS_MS));
    },
    [dismiss],
  );
  const pause = useCallback((id: number) => {
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  const show = useCallback(
    (variant: Variant, message: string, opts?: ToastOptions) => {
      const id = nextId.current++;
      setToasts((ts) => [...ts, { id, variant, message, ...opts }]);
      arm(id);
    },
    [arm],
  );

  const success = useCallback(
    (message: string, opts?: ToastOptions) => show("success", message, opts),
    [show],
  );
  const error = useCallback(
    (message: string, opts?: ToastOptions) => show("error", message, opts),
    [show],
  );

  return (
    <ToastContext.Provider value={{ show, success, error }}>
      {children}
      {/* A persistent polite live region (always in the DOM) so screen readers
          reliably announce toasts as they're inserted; aria-atomic=false keeps
          it to just the new toast, not a re-read of all of them. */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            onMouseEnter={() => pause(toast.id)}
            onMouseLeave={() => arm(toast.id)}
            onFocus={() => pause(toast.id)}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) arm(toast.id);
            }}
            className="pointer-events-auto flex w-full max-w-sm animate-fade-up items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 shadow-lg dark:border-slate-700 dark:bg-slate-800"
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                toast.variant === "success"
                  ? "bg-brand-400 text-slate-900"
                  : "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300"
              }`}
            >
              {toast.variant === "success" ? (
                <Check aria-hidden className="h-4 w-4" />
              ) : (
                <TriangleAlert aria-hidden className="h-4 w-4" />
              )}
            </span>
            <span className="min-w-0 flex-1 text-sm font-medium text-slate-900 dark:text-slate-100">
              {toast.message}
            </span>
            {toast.to && toast.actionLabel && (
              <Link
                to={toast.to}
                onClick={() => dismiss(toast.id)}
                className="shrink-0 text-sm font-bold text-brand-600 hover:text-brand-700 hover:underline dark:text-brand-400 dark:hover:text-brand-300"
              >
                {toast.actionLabel}
              </Link>
            )}
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              aria-label={t("Dismiss")}
              className="shrink-0 rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            >
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
