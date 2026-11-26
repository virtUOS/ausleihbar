// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api";
import { formatTime } from "../dates";
import type { BookingItem } from "../types";

/** Translated message for a refused check-in (409 `code`, see lending.checkin). */
export function checkinErrorMessage(e: unknown, t: TFunction): string {
  const code = e instanceof ApiError ? (e.data as { code?: string } | undefined)?.code : undefined;
  switch (code) {
    case "too_early":
      return t("Check-in opens 15 minutes before the start.");
    case "too_late":
      return t("The check-in time has passed.");
    case "not_confirmed":
      return t("The booking is not confirmed yet.");
    case "already":
      return t("Already checked in.");
    case "inactive":
      return t("This booking position is no longer active.");
    case "not_required":
      return t("This item does not need a check-in.");
    default:
      return e instanceof Error ? e.message : String(e);
  }
}

/** Check-in state of a flagged item as a small badge; nothing for other items. */
export function CheckinBadge({ item }: { item: BookingItem }) {
  const { t } = useTranslation();
  if (!item.checkin_required || item.dropped) return null;
  let text: string | null = null;
  let tone = "text-slate-500 dark:text-slate-400";
  if (item.released || item.checkin_state === "released") {
    text = t("Not used");
    tone = "text-red-700 dark:text-red-300";
  } else if (item.checked_in_at) {
    text = t("Checked in {{time}}", { time: formatTime(item.checked_in_at) });
    tone = "text-green-700 dark:text-green-300";
  } else if (item.checkin_state === "late") {
    text = t("Late – release at {{time}}", { time: formatTime(item.checkin_deadline) });
    tone = "text-amber-700 dark:text-amber-300";
  }
  if (!text) return null;
  return <span className={`text-xs font-medium ${tone}`}>{text}</span>;
}
