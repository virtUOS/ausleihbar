// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { useConfirm } from "./ConfirmDialog";

/** Ask before ending a self-service on-site use early (#167); shared by the
 *  borrower pages and the lending desk. Resolves true when confirmed. */
export function useConfirmEndUse() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  return (title: string) =>
    confirm({
      title: t("End use of {{title}}?", { title }),
      message: t("The rest of the period will be released for others. This can't be undone."),
      confirmLabel: t("End use"),
      cancelLabel: t("Keep using"),
      danger: true,
    });
}

/** Small inline "End use" button for an endable item (`can_end_use`, #167). */
export function EndUseButton({
  onClick,
  disabled,
  className = "",
}: {
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-full border border-slate-300 px-2.5 py-0.5 text-xs font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800 ${className}`}
    >
      {t("End use")}
    </button>
  );
}
