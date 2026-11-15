// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LampDesk, Settings } from "lucide-react";
import { useAuth } from "../auth";
import { DeskUserSettings } from "../desks/components/DeskUserSettings";

/** The person's own settings (account menu → "Settings"), one section per
 *  area. Only desksharing has personal settings so far; other areas add
 *  their section here. Language and appearance stay in the account menu. */
export function SettingsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { hash } = useLocation();
  const hasDesks = (user?.desk_pool_ids?.length ?? 0) > 0;

  // Links like `/settings#desksharing` jump to their section.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);

  return (
    <div className="pb-10">
      <h1 className="mb-1 flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-slate-100">
        <Settings aria-hidden className="h-5 w-5 text-slate-500 dark:text-slate-300" />
        {t("Settings")}
      </h1>
      <p className="mb-6 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
        {t("Your personal settings. Language and appearance are in the account menu.")}
      </p>

      {hasDesks ? (
        <section id="desksharing" aria-labelledby="settings-desks" className="max-w-3xl scroll-mt-20">
          <h2
            id="settings-desks"
            className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-slate-100"
          >
            <LampDesk aria-hidden className="h-5 w-5 text-slate-500 dark:text-slate-300" />
            {t("Desksharing")}
          </h2>
          <DeskUserSettings />
        </section>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("There are no further settings for you yet.")}</p>
      )}
    </div>
  );
}
