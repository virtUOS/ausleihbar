// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { CalendarDays, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { LendingType } from "../types";

/** Lending type as an icon (calendar = daily, clock = hourly, #19). The text
 *  label is exposed to screen readers and as a tooltip. */
export function LendingTypeIcon({
  type,
  className = "h-4 w-4",
}: {
  type: LendingType;
  className?: string;
}) {
  const { t } = useTranslation();
  const label = type === "hours" ? t("Hourly lending") : t("Daily lending");
  const Icon = type === "hours" ? Clock : CalendarDays;
  return (
    <span title={label} className="inline-flex shrink-0 items-center text-slate-500 dark:text-slate-400">
      <Icon aria-hidden className={className} />
      <span className="sr-only">{label}</span>
    </span>
  );
}
