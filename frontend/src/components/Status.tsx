// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Small helpers for loading, error and empty states. */

import i18n from "../i18n";

export function Loading({ label = i18n.t("Loading…") }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-10" role="status">
      <span
        aria-hidden
        className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-brand-500 dark:border-slate-700 dark:border-t-brand-400"
      />
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="my-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
      {message}
    </div>
  );
}

/** Friendly empty state: a soft emoji moment instead of a bare sentence. */
export function Empty({ label, emoji = "🪺" }: { label: string; emoji?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <span aria-hidden className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-3xl dark:bg-brand-900/30">
        {emoji}
      </span>
      <p className="max-w-xs text-sm text-slate-500 dark:text-slate-400">{label}</p>
    </div>
  );
}
