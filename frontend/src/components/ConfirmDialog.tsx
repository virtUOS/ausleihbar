// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";

export type ConfirmOptions = {
  /** Headline; defaults to a generic "Please confirm". */
  title?: string;
  /** The question / consequence shown to the user. */
  message: string;
  /** Label of the affirmative button; defaults to "Confirm". */
  confirmLabel?: string;
  /** Label of the dismissive button; defaults to "Cancel". */
  cancelLabel?: string;
  /** Render the affirmative button in a destructive (red) style. */
  danger?: boolean;
};

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(() => Promise.resolve(false));

/** Returns an async `confirm(options)` that resolves to true/false. Replaces the
 *  native `window.confirm` with a themed, accessible dialog. Usage:
 *
 *    const confirm = useConfirm();
 *    if (!(await confirm({ message: t("Delete X?"), danger: true }))) return;
 */
export function useConfirm(): ConfirmFn {
  return useContext(ConfirmContext);
}

/** Provides a single shared confirmation dialog for the whole app. Mount it high
 *  in the tree so any view can call `useConfirm()`. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    // If a dialog is somehow already open, settle its promise (as cancelled)
    // before replacing it, so the earlier caller never hangs.
    resolver.current?.(false);
    setOptions(opts);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const settle = useCallback((ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    setOptions(null);
  }, []);

  // While open: focus the safe (cancel) action, trap Tab within the dialog,
  // close on Escape, lock scroll, and restore focus to the trigger on close.
  useEffect(() => {
    if (!options) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        settle(false);
        return;
      }
      if (e.key === "Tab") {
        const focusables = dialogRef.current?.querySelectorAll<HTMLElement>("button");
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      previouslyFocused?.focus?.();
    };
  }, [options, settle]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {options && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          aria-describedby="confirm-dialog-message"
          onClick={() => settle(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        >
          <div
            ref={dialogRef}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900"
          >
            <h2
              id="confirm-dialog-title"
              className="text-lg font-semibold text-slate-900 dark:text-slate-100"
            >
              {options.title ?? t("Please confirm")}
            </h2>
            <p
              id="confirm-dialog-message"
              className="mt-2 text-sm text-slate-600 dark:text-slate-300"
            >
              {options.message}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                ref={cancelRef}
                type="button"
                onClick={() => settle(false)}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {options.cancelLabel ?? t("Cancel")}
              </button>
              <button
                type="button"
                onClick={() => settle(true)}
                className={
                  options.danger
                    ? "rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                    : "rounded-lg bg-brand-400 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-brand-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
                }
              >
                {options.confirmLabel ?? t("Confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
