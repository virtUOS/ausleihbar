// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Copy, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

/**
 * Compact icon buttons for row actions in the admin/lending lists. Icon-only to
 * keep dense tables tidy; the visible label moves into `title`/`aria-label` so
 * the action stays accessible (a pointer tooltip + a name for screen readers).
 */
const base =
  "inline-flex items-center justify-center rounded-md p-2 transition-colors duration-150 disabled:opacity-40";

/** Pencil button for "Edit". */
export function EditButton({
  onClick,
  disabled,
  label,
  className = "",
}: {
  onClick: () => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const text = label ?? t("Edit");
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={text}
      aria-label={text}
      className={`${base} text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 ${className}`}
    >
      <Pencil aria-hidden className="h-4 w-4" />
    </button>
  );
}

/** Copy button for "Duplicate". */
export function DuplicateButton({
  onClick,
  disabled,
  label,
  className = "",
}: {
  onClick: () => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const text = label ?? t("Duplicate");
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={text}
      aria-label={text}
      className={`${base} text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 ${className}`}
    >
      <Copy aria-hidden className="h-4 w-4" />
    </button>
  );
}

/** Trash button for "Delete" — neutral by default, turning red on intent. */
export function DeleteButton({
  onClick,
  disabled,
  label,
  className = "",
}: {
  onClick: () => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const text = label ?? t("Delete");
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={text}
      aria-label={text}
      className={`${base} text-slate-400 hover:bg-red-50 hover:text-red-600 dark:text-slate-300 dark:hover:bg-red-950/40 dark:hover:text-red-300 ${className}`}
    >
      <Trash2 aria-hidden className="h-4 w-4" />
    </button>
  );
}
