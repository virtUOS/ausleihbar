// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import type { NotificationChannel, NotificationPreferences } from "./types";

/** Event keys in display order with their (translated) labels. */
const EVENTS: [string, string, string][] = [
  ["daily_summary", "Daily summary of your reservations", "Your bookings of the day, every morning."],
  ["grace_nudge", "Reminder to check in", "When you have not checked in yet, with the links \"I will be late\" and \"Release\"."],
  ["released_no_show", "Reservation released because of no check-in", "Your place was released because you did not check in."],
  ["released_other", "Reservation released by someone else", "Someone else released your reservation."],
  ["booked_for_you", "Someone booked a place for you", "A colleague or the department booked a place in your name."],
  ["admin_changed", "A department admin changed your reservation", "Your place or time was changed by the department."],
  ["swap_request", "Swap request for your place", "Someone asks to swap places with you."],
  ["swap_answer", "Answer to your swap request", "The answer to a swap you requested."],
  ["release_request", "Request to release your place", "Someone asks you to release your place."],
  ["release_answer", "Answer to your release request", "The answer to a release you requested."],
  ["series_extension_due", "Series ending soon: extension reminder", "Your recurring reservation ends soon and can be extended."],
];

/** Per-event mail preference (push is not offered yet). */
export function NotificationSettingsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const { data, error } = useFetch(() => desksApi.notificationPreferences(), []);
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const profile = useFetch(() => desksApi.profile(), []);
  const [hideName, setHideName] = useState<boolean | null>(null);
  const [savingHide, setSavingHide] = useState(false);

  useEffect(() => {
    if (profile.data) setHideName((cur) => cur ?? profile.data!.hide_name);
  }, [profile.data]);

  async function changeHide(value: boolean) {
    setSavingHide(true);
    try {
      const res = await desksApi.setHideName(value);
      setHideName(res.hide_name);
      toast.success(t("Saved."));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setSavingHide(false);
    }
  }

  // Seed the editable copy once; later language switches refetch nothing visible.
  useEffect(() => {
    if (data) setPrefs((cur) => cur ?? data);
  }, [data]);

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
    <div className="space-y-8">
    <section aria-labelledby="notif-title">
      <h2 id="notif-title" className="mb-1 text-lg font-bold text-slate-900 dark:text-slate-100">
        {t("Notifications")}
      </h2>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        {t("Choose for each event whether you want to be notified by mail.")}
      </p>
      <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
        {EVENTS.map(([event, label, desc]) => (
          <li key={event} className="flex flex-wrap items-center justify-between gap-2 p-3">
            <div className="min-w-0 flex-1">
              <label htmlFor={`n-${event}`} className="block text-sm font-medium text-slate-800 dark:text-slate-100">
                {t(label)}
              </label>
              <p className="text-xs text-slate-600 dark:text-slate-300">{t(desc)}</p>
            </div>
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

    <section aria-labelledby="privacy-title">
      <h2 id="privacy-title" className="mb-3 text-lg font-bold text-slate-900 dark:text-slate-100">
        {t("Privacy")}
      </h2>
      {profile.error && <ErrorBox message={profile.error} />}
      {hideName === null && !profile.error && <Loading />}
      {hideName !== null && (
        <label className="flex min-h-[44px] items-start gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
          <input
            type="checkbox"
            checked={hideName}
            disabled={savingHide}
            onChange={(e) => changeHide(e.target.checked)}
            className="mt-0.5 h-5 w-5 shrink-0"
          />
          <span className="min-w-0">
            <span className="block text-sm font-medium text-slate-800 dark:text-slate-100">
              {t("Hide my name at desks")}
            </span>
            <span className="block text-xs text-slate-600 dark:text-slate-300">
              {t("Names stay visible for meeting room bookings. Department admins will not see your name at desks either.")}
            </span>
          </span>
        </label>
      )}
    </section>
    </div>
  );
}
