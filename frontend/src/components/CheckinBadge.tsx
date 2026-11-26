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

/** Label of a dropped position (never handed out): a release for a missed
 *  check-in reads "Not used", anything else "Cancelled". */
export function droppedLabel(item: { released?: boolean }, t: TFunction): string {
  return item.released ? t("Not used") : t("Cancelled");
}

/** Text and tone of a flagged item's check-in badge, or null when it shows
 *  nothing (callers use it to decide whether a separator is needed).
 *  Released items are dropped too but keep their "Not used" badge; "expired"
 *  (deadline passed, release pending) reads the same. */
export function checkinBadgeLabel(
  item: BookingItem,
  t: TFunction,
): { text: string; tone: string } | null {
  if (!item.checkin_required || (item.dropped && !item.released)) return null;
  if (
    item.released ||
    item.checkin_state === "released" ||
    item.checkin_state === "expired"
  ) {
    return { text: t("Not used"), tone: "text-red-700 dark:text-red-300" };
  }
  if (item.checked_in_at) {
    return {
      text: t("Checked in {{time}}", { time: formatTime(item.checked_in_at) }),
      tone: "text-green-700 dark:text-green-300",
    };
  }
  if (item.checkin_state === "late") {
    return {
      text: t("Late – release at {{time}}", { time: formatTime(item.checkin_deadline) }),
      tone: "text-amber-700 dark:text-amber-300",
    };
  }
  return null;
}

/** Check-in state of a flagged item as a small badge; nothing for other items.
 *  ``separator`` puts " · " in front — only when the badge shows something. */
export function CheckinBadge({ item, separator = false }: { item: BookingItem; separator?: boolean }) {
  const { t } = useTranslation();
  const label = checkinBadgeLabel(item, t);
  if (!label) return null;
  return (
    <>
      {separator && " · "}
      <span className={`text-xs font-medium ${label.tone}`}>{label.text}</span>
    </>
  );
}
