// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import type { NotificationChannel, NotificationPreferences } from "./types";

/** Event keys in display order with their (translated) labels. */
const EVENTS: [string, string][] = [
  ["daily_summary", "Daily summary of your reservations"],
  ["grace_nudge", "Reminder to check in"],
  ["released_no_show", "Reservation released because of no check-in"],
  ["released_other", "Reservation released by someone else"],
  ["booked_for_you", "Someone booked a place for you"],
  ["admin_changed", "A department admin changed your reservation"],
  ["swap_request", "Swap request for your place"],
  ["swap_answer", "Answer to your swap request"],
  ["release_request", "Request to release your place"],
  ["release_answer", "Answer to your release request"],
  ["series_extension_due", "Series ending soon: extension reminder"],
];

/** Per-event mail preference (push is not offered yet). */
export function NotificationSettingsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    desksApi
      .notificationPreferences()
      .then(setPrefs)
      .catch((e) => setError(e instanceof Error ? e.message : t("The request failed.")));
  }, [t]);

  async function change(event: string, channel: NotificationChannel) {
    const before = prefs;
    setPrefs((p) => (p ? { ...p, [event]: channel } : p));
    try {
      setPrefs(await desksApi.setNotificationPreferences({ [event]: channel }));
    } catch (e) {
      setPrefs(before);
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  if (error) return <ErrorBox message={error} />;
  if (!prefs) return <Loading />;

  return (
    <section aria-labelledby="notif-title">
      <h2 id="notif-title" className="mb-1 text-lg font-bold text-slate-900 dark:text-slate-100">
        {t("Desk notifications")}
      </h2>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        {t("Choose for each event whether you want to be notified by mail.")}
      </p>
      <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
        {EVENTS.map(([event, label]) => (
          <li key={event} className="flex flex-wrap items-center justify-between gap-2 p-3">
            <label htmlFor={`n-${event}`} className="min-w-0 flex-1 text-sm text-slate-800 dark:text-slate-100">
              {t(label)}
            </label>
            <select
              id={`n-${event}`}
              value={prefs[event] ?? "mail"}
              onChange={(e) => change(event, e.target.value as NotificationChannel)}
              className="min-h-[44px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="mail">{t("Mail")}</option>
              <option value="off">{t("Off")}</option>
            </select>
          </li>
        ))}
      </ul>
    </section>
  );
}
