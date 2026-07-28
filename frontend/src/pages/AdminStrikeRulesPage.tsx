// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { useAuth } from "../auth";
import { AdminTabs } from "../components/AdminTabs";
import { StrikeRulesEditor } from "../components/StrikeRulesEditor";

export function AdminStrikeRulesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }
  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Strike rules")}</h2>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t(
          "How long a strike counts and how repeated strikes suspend a borrower. Strikes themselves are issued at the lending desk and managed per user on the Users tab.",
        )}
      </p>
      <StrikeRulesEditor />
    </div>
  );
}
