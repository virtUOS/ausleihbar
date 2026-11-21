// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

/** "Persönlich · ‹owner›" — marks a personal pool (LTI course pools). */
export function PersonalPoolBadge({
  owner,
  className = "",
}: {
  owner: { id: number; name: string } | null;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-block rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-800 dark:bg-brand-900/30 dark:text-brand-200 ${className}`}
    >
      {owner ? t("Personal · {{owner}}", { owner: owner.name }) : t("Personal")}
    </span>
  );
}
