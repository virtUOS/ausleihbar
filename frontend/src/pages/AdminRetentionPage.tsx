// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { AdminTabs } from "../components/AdminTabs";
import { ErrorBox, Loading } from "../components/Status";
import type { RetentionSetting } from "../types";

/** Admin data-retention policy: anonymize accounts inactive past a window
 *  (years), with no open lending process. Off until enabled here. */
export function AdminRetentionPage() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const [setting, setSetting] = useState<RetentionSetting | null>(null);
  const [years, setYears] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");

  useEffect(() => {
    api
      .getRetentionSetting()
      .then((s) => {
        setSetting(s);
        setYears(Math.max(1, Math.round(s.retention_days / 365)));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, []);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  async function save(next: Partial<RetentionSetting>) {
    setStatus("saving");
    setError(null);
    try {
      const updated = await api.updateRetentionSetting({
        enabled: next.enabled ?? setting?.enabled ?? false,
        retention_days: next.retention_days ?? years * 365,
      });
      setSetting(updated);
      setYears(Math.max(1, Math.round(updated.retention_days / 365)));
      setStatus("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("Save failed."));
      setStatus("idle");
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Data retention")}</h2>
      <p className="mb-4 max-w-2xl text-xs text-slate-500 dark:text-slate-400">
        {t(
          "Automatically anonymize accounts that have been inactive for the period below and have no open lending processes. All personal data is removed; the device and booking history is kept under a neutral placeholder (“Gelöschter Nutzer”). Administrator accounts are never affected. This is irreversible.",
        )}
      </p>

      {error && <ErrorBox message={error} />}
      {!setting ? (
        <Loading />
      ) : (
        <div className="max-w-xl space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900">
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={setting.enabled}
              onChange={(e) => save({ enabled: e.target.checked })}
              className="mt-0.5 h-4 w-4"
            />
            <span className="text-sm text-slate-800 dark:text-slate-100">
              {t("Enable automatic anonymization")}
              <span className="block text-xs text-slate-500 dark:text-slate-400">
                {setting.enabled ? t("On — runs on the scheduled job.") : t("Off — nothing is anonymized.")}
              </span>
            </span>
          </label>

          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              {t("Anonymize after this many years of inactivity")}
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="number"
                min={1}
                max={20}
                value={years}
                onChange={(e) => setYears(Math.max(1, Number(e.target.value) || 1))}
                className="w-24 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
              <button
                type="button"
                onClick={() => save({ retention_days: years * 365 })}
                disabled={status === "saving"}
                className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
              >
                {status === "saving" ? t("Saving…") : t("Save")}
              </button>
              {status === "saved" && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">{t("Saved")}</span>
              )}
            </div>
          </div>

          <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800/50 dark:text-slate-300">
            {t("With the current window, {{n}} account(s) would be anonymized now.", {
              n: setting.affected_now ?? 0,
            })}
          </p>
        </div>
      )}
    </div>
  );
}
