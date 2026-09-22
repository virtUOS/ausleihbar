// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

/** Visually set-off container for an optional AI-assist feature. Carries a
 *  consistent heading (sparkle icon + title) and a note that the assistance is
 *  optional, so the two AI helpers (attribute suggestions, PDF extraction) look
 *  and read the same. */
export function AiAssistPanel({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border border-brand-300 bg-brand-50/60 p-3 dark:border-brand-500/40 dark:bg-brand-500/5">
      <div className="flex items-center gap-1.5">
        <Sparkles aria-hidden className="h-4 w-4 text-brand-600 dark:text-brand-400" />
        <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">{title}</p>
      </div>
      <p className="mt-0.5 mb-2 text-xs text-slate-600 dark:text-slate-300">
        {t("Optional AI assistance — you don't have to use it.")}
      </p>
      {children}
    </div>
  );
}
