// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Shared, locale-aware date formatting for display (issue #22): dates follow
 *  the active UI language (e.g. 21.09.2026 in German, 09/21/2026 in English)
 *  instead of a hardcoded locale. Internal ISO values (date inputs, keys) keep
 *  using the fixed "en-CA" formatting elsewhere and must not use these. */

import i18n from "./i18n";

/** A date without time, in the active UI language. Returns "–" for empty.
 *  A date-only ISO string (yyyy-mm-dd) is a local calendar date, parsed as such
 *  to avoid a UTC-midnight off-by-one in negative-offset timezones. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const d = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(iso);
  return d.toLocaleDateString(i18n.language, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** A day with its weekday, in the active UI language (e.g. "Do., 22.10.2026" /
 *  "Thu, 10/22/2026") — for headings of a single day (#151). Date-only ISO is
 *  parsed as a local date like `formatDate`. Returns "–" for empty. */
export function formatDayWithWeekday(iso: string | null | undefined): string {
  if (!iso) return "–";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const d = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(iso);
  return d.toLocaleDateString(i18n.language, {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** The last moment an exclusive period end (`[start, end)`) still covers, in
 *  the active UI language. A midnight-aligned end (day bookings) shows the day
 *  before it, date only; any other end (hourly bookings) shows date + time of
 *  the end itself (e.g. "11.10.2026, 16:00"). Returns "–" for empty. */
export function formatPeriodEnd(iso: string | null | undefined): string {
  if (!iso) return "–";
  const end = new Date(iso);
  if (Number.isNaN(end.getTime())) return "–";
  const midnight =
    end.getHours() === 0 && end.getMinutes() === 0 && end.getSeconds() === 0 && end.getMilliseconds() === 0;
  if (midnight) {
    return new Date(Date.parse(iso) - 1).toLocaleDateString(i18n.language, {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }
  return end.toLocaleString(i18n.language, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A date with time, in the active UI language. Returns "–" for empty. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString(i18n.language, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
