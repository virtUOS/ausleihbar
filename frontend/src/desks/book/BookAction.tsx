// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ApiError } from "../../api";
import { formatDate } from "../../dates";

/** A refused booking as the page shows it: the message and, for taken or
 *  unavailable dates, the dates per place. */
export interface BookProblem {
  code: string;
  message: string;
  /** "Place: date, date" lines. */
  details: string[];
}

/** Dates grouped by place, as "Place: 01.12., 02.12." lines. */
export function datesByPlace(
  slots: { day: string; place_id: number }[],
  placeName: (id: number) => string,
): string[] {
  const by = new Map<number, string[]>();
  for (const s of slots) by.set(s.place_id, [...(by.get(s.place_id) ?? []), s.day]);
  return [...by].map(([id, days]) => `${placeName(id)}: ${days.sort().map((d) => formatDate(d)).join(", ")}`);
}

/** Translate a refused `bookDays` or series call (409 bodies carry the code and its
 *  numbers; the backend's own detail has none). Null for other errors. */
export function bookProblem(e: unknown, t: TFunction, placeName: (id: number) => string): BookProblem | null {
  if (!(e instanceof ApiError) || e.status !== 409) return null;
  const body = (e.data ?? {}) as {
    code?: string;
    limit?: number;
    open_until?: string;
    day?: string;
    taken?: { day: string; place_id: number }[];
    unavailable?: { day: string; place_id: number }[];
  };
  const code = body.code ?? "";
  switch (code) {
    case "taken":
      if (body.unavailable?.length) {
        return {
          code,
          message: t("Some dates cannot be booked or requested:"),
          details: datesByPlace(body.unavailable, placeName),
        };
      }
      return {
        code,
        message: t("Meanwhile these dates were booked by someone else:"),
        details: datesByPlace(body.taken ?? [], placeName),
      };
    case "advance_days":
      return {
        code,
        message: t("Beyond {{date}} you may book at most {{count}} days. Nothing was booked.", {
          count: body.limit ?? 0,
          date: formatDate(body.open_until),
        }),
        details: [],
      };
    case "advance_places":
      return {
        code,
        message: t("Beyond the booking window you may book at most {{count}} places per day ({{date}}). Nothing was booked.", {
          count: body.limit ?? 0,
          date: formatDate(body.day),
        }),
        details: [],
      };
    case "series_window":
      return {
        code,
        message: t("A series may reach at most until {{date}}. Nothing was booked.", {
          date: formatDate(body.open_until),
        }),
        details: [],
      };
    default:
      return {
        code,
        message: body.day ? `${e.message} (${formatDate(body.day)})` : e.message,
        details: [],
      };
  }
}

/** Limits an assistant exceeded on purpose when booking for `name` (201
 *  warnings), as messages. */
export function limitWarnings(warnings: string[], t: TFunction, name: string): string[] {
  const out: string[] = [];
  if (warnings.includes("advance_days"))
    out.push(t("{{name}} now has more days booked beyond the booking window than allowed.", { name }));
  if (warnings.includes("advance_places"))
    out.push(t("{{name}} now has more places on one day beyond the booking window than allowed.", { name }));
  if (warnings.includes("series_window"))
    out.push(t("The series for {{name}} reaches beyond the booking window.", { name }));
  return out;
}

/** Taken dates that will be asked of their holders: the dates per place, how
 *  many are booked now and how many requested, and "Show my name". */
export function RequestNotice({
  lines,
  bookedCount,
  requestedCount,
  showName,
  onShowName,
}: {
  /** "Place: date, date" lines (`datesByPlace`). */
  lines: string[];
  bookedCount: number;
  requestedCount: number;
  showName: boolean;
  onShowName: (on: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
        <p className="font-medium">{t("These dates are already booked by someone else:")}</p>
        <ul className="mt-1 list-disc pl-5">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-1">
          {bookedCount > 0
            ? `${t("{{count}} dates will be booked now,", { count: bookedCount })} ${t(
                "for {{count}} dates the holder is asked to release them.",
                { count: requestedCount },
              )}`
            : t("For {{count}} dates the holder is asked to release them.", { count: requestedCount })}
        </p>
      </div>
      <label className="mt-2 flex min-h-[44px] items-center gap-2 text-sm text-slate-800 dark:text-slate-100">
        <input
          type="checkbox"
          checked={showName}
          onChange={(e) => onShowName(e.target.checked)}
          className="h-5 w-5 accent-brand-600"
        />
        {t("Show my name")}
      </label>
    </>
  );
}

/** The last step: optional comment, a notice (problems, taken dates) and the
 *  primary action. */
export function BookAction({
  comment,
  onComment,
  label,
  disabled,
  onSubmit,
  notice,
  problem,
}: {
  comment: string;
  onComment: (text: string) => void;
  label: string;
  disabled: boolean;
  onSubmit: () => void;
  /** Shown above the button (e.g. why it is disabled). */
  notice?: ReactNode;
  problem?: BookProblem | null;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <label htmlFor="book-comment" className="sr-only">
        {t("Comment")}
      </label>
      <input
        id="book-comment"
        type="text"
        maxLength={200}
        value={comment}
        onChange={(e) => onComment(e.target.value)}
        className="min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
      />
      {problem && (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
        >
          <p className="font-medium">{problem.message}</p>
          {problem.details.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {problem.details.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {notice && <div className="mt-4">{notice}</div>}
      <button
        type="button"
        disabled={disabled}
        onClick={onSubmit}
        className="mt-4 min-h-[48px] w-full rounded-full bg-brand-500 px-6 text-base font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50 sm:w-auto"
      >
        {label}
      </button>
    </div>
  );
}
