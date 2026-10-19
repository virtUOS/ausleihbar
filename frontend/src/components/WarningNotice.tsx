// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { TriangleAlert, X } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Persistent inline warning (amber) with an optional dismiss button. Use it
 *  for partial failures a user must not miss; toasts vanish too quickly. */
export function WarningNotice({
  message,
  onDismiss,
  className = "",
}: {
  message: string;
  onDismiss?: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200 ${className}`}
    >
      <TriangleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="min-w-0 flex-1 break-words">{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={t("Dismiss")}
          className="shrink-0 rounded p-0.5 hover:bg-amber-100 dark:hover:bg-amber-900/50"
        >
          <X aria-hidden className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
