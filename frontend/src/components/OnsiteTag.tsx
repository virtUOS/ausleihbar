// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { MapPin } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Small pill marking an item that is used on site instead of being lent out
 *  (#116). `short` uses the compact "On site" wording for tight lists. */
export function OnsiteTag({ short = false }: { short?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-200">
      <MapPin aria-hidden className="h-3 w-3" />
      {short ? t("On site") : t("On-site use")}
    </span>
  );
}
