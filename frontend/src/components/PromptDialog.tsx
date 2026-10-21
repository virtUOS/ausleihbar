// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { useModal } from "./useModal";

export type PromptOptions = {
  /** Headline; defaults to a generic "Please enter a value". */
  title?: string;
  /** The question shown above the field. */
  message: string;
  /** Accessible label of the field; defaults to the message. */
  label?: string;
  placeholder?: string;
  /** Refuse an empty (whitespace-only) answer. */
  required?: boolean;
  confirmLabel?: string;
  /** Label of the dismissive button; defaults to "Cancel". */
  cancelLabel?: string;
  /** Render the affirmative button in a destructive (red) style. */
  danger?: boolean;
  /** Use a multi-line textarea instead of a single-line input. */
  multiline?: boolean;
};

type PromptFn = (options: PromptOptions) => Promise<string | null>;

const PromptContext = createContext<PromptFn>(() => Promise.resolve(null));

/** Returns an async `askText(options)` that resolves to the entered (trimmed)
 *  text, or null when cancelled. Replaces the native text-entry dialog. */
export function usePrompt(): PromptFn {
  return useContext(PromptContext);
}

/** Provides a single shared prompt dialog for the whole app (mount next to
 *  `ConfirmProvider`). */
export function PromptProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [options, setOptions] = useState<PromptOptions | null>(null);
  const [value, setValue] = useState("");
  const resolver = useRef<((v: string | null) => void) | null>(null);
  const fieldRef = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLFormElement>(null);

  const askText = useCallback<PromptFn>((opts) => {
    resolver.current?.(null);
    setValue("");
    setOptions(opts);
    return new Promise<string | null>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const settle = useCallback((result: string | null) => {
    resolver.current?.(result);
    resolver.current = null;
    setOptions(null);
  }, []);

  useModal(!!options, dialogRef, () => settle(null), fieldRef);

  const trimmed = value.trim();
  const canSubmit = !options?.required || trimmed.length > 0;
  const fieldClass =
    "mt-3 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500";

  return (
    <PromptContext.Provider value={askText}>
      {children}
      {options && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="prompt-dialog-title"
          aria-describedby="prompt-dialog-message"
          onClick={() => settle(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        >
          <form
            ref={dialogRef}
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => {
              e.preventDefault();
              if (canSubmit) settle(trimmed);
            }}
            className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900"
          >
            <h2
              id="prompt-dialog-title"
              className="text-lg font-semibold text-slate-900 dark:text-slate-100"
            >
              {options.title ?? t("Please enter a value")}
            </h2>
            <p
              id="prompt-dialog-message"
              className="mt-2 text-sm text-slate-600 dark:text-slate-300"
            >
              {options.message}
            </p>
            {options.multiline ? (
              <textarea
                ref={fieldRef}
                value={value}
                rows={4}
                aria-label={options.label ?? options.message}
                placeholder={options.placeholder}
                onChange={(e) => setValue(e.target.value)}
                className={fieldClass}
              />
            ) : (
              <input
                ref={fieldRef}
                value={value}
                aria-label={options.label ?? options.message}
                placeholder={options.placeholder}
                onChange={(e) => setValue(e.target.value)}
                className={fieldClass}
              />
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => settle(null)}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {options.cancelLabel ?? t("Cancel")}
              </button>
              <button
                type="submit"
                disabled={!canSubmit}
                className={
                  options.danger
                    ? "rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-40"
                    : "rounded-lg bg-brand-400 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-brand-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:opacity-40"
                }
              >
                {options.confirmLabel ?? t("Confirm")}
              </button>
            </div>
          </form>
        </div>
      )}
    </PromptContext.Provider>
  );
}
