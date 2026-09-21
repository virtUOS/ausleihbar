// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

/** Drag handle + up/down arrow buttons for a reorderable table row. */
export function ReorderControls({
  onUp,
  onDown,
  isFirst,
  isLast,
  label,
}: {
  onUp: () => void;
  onDown: () => void;
  isFirst: boolean;
  isLast: boolean;
  label: string;
}) {
  const { t } = useTranslation();
  const arrow =
    "flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent";
  return (
    <div className="flex items-center gap-1.5">
      <span
        aria-hidden
        title={t("Drag to reorder")}
        className="cursor-grab select-none px-1 text-lg leading-none text-slate-400 dark:text-slate-400"
      >
        ⠿
      </span>
      <button
        type="button"
        onClick={onUp}
        disabled={isFirst}
        aria-label={t("Move {{label}} up", { label })}
        className={arrow}
      >
        ↑
      </button>
      <button
        type="button"
        onClick={onDown}
        disabled={isLast}
        aria-label={t("Move {{label}} down", { label })}
        className={arrow}
      >
        ↓
      </button>
    </div>
  );
}
