// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck } from "lucide-react";
import { formatDayWithWeekday, formatTime } from "../dates";
import { desksApi } from "./api";
import { tokenErrorMessage } from "./errors";
import type { ActionContext, DeskAction } from "./types";

const linkBtn =
  "inline-flex min-h-[44px] items-center justify-center rounded-full border border-slate-300 px-5 text-sm font-semibold text-slate-800 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-800";
const primaryBtn =
  "min-h-[44px] rounded-full bg-brand-500 px-5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50";

const CHIPS: { minutes: number; label: string }[] = [
  { minutes: 30, label: "+30 min" },
  { minutes: 60, label: "+1 h" },
  { minutes: 120, label: "+2 h" },
  { minutes: 180, label: "+3 h" },
];

/** `/desks/a/:token?action=later|release` — target of the mail links. Never
 *  acts on load (mail scanners prefetch links): the user confirms explicitly. */
export function ActionPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const [params] = useSearchParams();
  const action: DeskAction | null =
    params.get("action") === "later" ? "later" : params.get("action") === "release" ? "release" : null;
  const [ctx, setCtx] = useState<ActionContext | null>(null);
  const [ctxError, setCtxError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // Read-only: shows what the link is about and blocks wrong-user / expired
  // links before any click.
  useEffect(() => {
    let cancelled = false;
    desksApi
      .actionContext(token)
      .then((c) => !cancelled && setCtx(c))
      .catch((e) => !cancelled && setCtxError(tokenErrorMessage(e, t)));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const reservation = ctx?.reservation ?? null;
  const blocked =
    ctxError ??
    (ctx?.expired
      ? t("This link has expired because the reservation is over.")
      : reservation && reservation.status !== "active"
        ? t("The reservation was already released.")
        : null);

  async function run(act: DeskAction, until?: Date) {
    setBusy(true);
    setError(null);
    try {
      // Chips are offsets from now; the server rejects anything past the end.
      await desksApi.action(token, act, until?.toISOString());
      setDone(
        act === "release"
          ? t("The place is released.")
          : t("Noted. Your place stays reserved until {{time}}.", { time: formatTime(until!.toISOString()) }),
      );
    } catch (e) {
      setError(tokenErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  }

  const where = reservation
    ? `${reservation.place} · ${formatDayWithWeekday(reservation.start)} · ${formatTime(reservation.start)}–${formatTime(reservation.end)}`
    : null;
  const end = reservation ? new Date(reservation.end).getTime() : Infinity;
  const chips = CHIPS.filter((c) => Date.now() + c.minutes * 60_000 <= end);

  return (
    <section aria-labelledby="action-title" className="mx-auto max-w-md">
      <h2 id="action-title" className="mb-1 text-lg font-bold text-slate-900 dark:text-slate-100">
        {action === "release" ? t("Release place") : action === "later" ? t("I will be late") : t("Reservation")}
      </h2>
      {where && <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{where}</p>}

      {done ? (
        <div role="status" className="rounded-2xl border border-green-300 bg-green-50 p-6 text-center text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100">
          <CircleCheck aria-hidden className="mx-auto mb-3 h-12 w-12" />
          <p className="text-lg font-bold">{done}</p>
        </div>
      ) : blocked ? (
        <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
          <CircleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
          {blocked}
        </p>
      ) : action === null ? (
        <p role="alert" className="text-sm text-slate-700 dark:text-slate-200">{t("This link is invalid.")}</p>
      ) : (
        <>
          {action === "release" ? (
            <>
              <p className="mb-4 text-sm text-slate-700 dark:text-slate-200">
                {t("Do you want to release this place so others can use it?")}
              </p>
              <button type="button" disabled={busy} onClick={() => run("release")} className={primaryBtn}>
                {t("Release")}
              </button>
            </>
          ) : (
            <>
              <p className="mb-3 text-sm text-slate-700 dark:text-slate-200">
                {t("How long until you arrive? Your place stays reserved for you.")}
              </p>
              <div className="flex flex-wrap gap-2">
                {chips.map((c) => (
                  <button
                    key={c.minutes}
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      // Recomputed at click time, capped at the reservation end.
                      const until = new Date(Math.min(Date.now() + c.minutes * 60_000, end));
                      void run("later", until);
                    }}
                    className={primaryBtn}
                  >
                    {t(c.label)}
                  </button>
                ))}
              </div>
              {chips.length === 0 && (
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {t("Your reservation ends soon. There is nothing left to postpone.")}
                </p>
              )}
            </>
          )}
          {error && (
            <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
              <CircleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </p>
          )}
        </>
      )}
      <div className="mt-6 flex flex-wrap gap-2">
        <Link to="/desks/mine" className={linkBtn}>
          {t("My reservations")}
        </Link>
        <Link to="/desks" className={linkBtn}>
          {t("Free now")}
        </Link>
      </div>
    </section>
  );
}
