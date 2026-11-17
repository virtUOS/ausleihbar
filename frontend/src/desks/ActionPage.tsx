// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CircleCheck } from "lucide-react";
import { formatDayWithWeekday, formatTime } from "../dates";
import { desksApi } from "./api";
import { TokenErrorNotice } from "./components/TokenErrorNotice";
import { resolveTokenError, type TokenError } from "./errors";
import { defaultLate, lateOptionLabel, lateOptions } from "./late";
import type { ActionContext, DeskAction } from "./types";

const linkBtn =
  "inline-flex min-h-[44px] items-center justify-center rounded-full border border-slate-300 px-5 text-sm font-semibold text-slate-800 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-800";
const primaryBtn =
  "min-h-[44px] rounded-full bg-brand-500 px-5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50";

const chipBtn =
  "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

/** `/desks/a/:token?action=later|release` — target of the mail links. Never
 *  acts on load (mail scanners prefetch links): the user confirms explicitly. */
export function ActionPage() {
  const { t, i18n } = useTranslation();
  const { token = "" } = useParams();
  const [params] = useSearchParams();
  const action: DeskAction | null =
    params.get("action") === "later" ? "later" : params.get("action") === "release" ? "release" : null;
  const [ctx, setCtx] = useState<ActionContext | null>(null);
  const [ctxError, setCtxError] = useState<TokenError | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<TokenError | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [lateMinutes, setLateMinutes] = useState<number | null>(null);

  // Read-only: shows what the link is about and blocks wrong-user / expired
  // links before any click.
  useEffect(() => {
    let cancelled = false;
    desksApi
      .actionContext(token)
      .then((c) => !cancelled && setCtx(c))
      .catch(async (e) => {
        const err = await resolveTokenError(e, t);
        if (!cancelled) setCtxError(err);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const reservation = ctx?.reservation ?? null;
  const blocked: TokenError | null =
    ctxError ??
    (ctx?.expired
      ? { message: t("This link has expired because the reservation is over."), login: false }
      : reservation && reservation.status !== "active"
        ? { message: t("The reservation was already released."), login: false }
        : null);

  async function run(act: DeskAction, until?: Date) {
    setBusy(true);
    setError(null);
    try {
      // The server rejects anything past the end.
      await desksApi.action(token, act, until?.toISOString());
      setDone(
        act === "release"
          ? t("The place is released.")
          : t("Noted. Your place stays reserved until {{time}}.", { time: formatTime(until!.toISOString()) }),
      );
    } catch (e) {
      setError(await resolveTokenError(e, t));
    } finally {
      setBusy(false);
    }
  }

  const where = reservation
    ? `${reservation.place} · ${formatDayWithWeekday(reservation.start)} · ${formatTime(reservation.start)}–${formatTime(reservation.end)}`
    : null;
  // Same steps as on the reservation card: 30-minute steps up to half the
  // booked time, counted from max(start, now); 1 h preselected.
  const options = reservation ? lateOptions(reservation.start, reservation.end, new Date()) : [];
  const selectedLate = options.some((o) => o.minutes === lateMinutes) ? lateMinutes : defaultLate(options);

  function saveLate() {
    if (!reservation) return;
    // Recompute at click time: the options are relative to "now".
    const fresh = lateOptions(reservation.start, reservation.end, new Date());
    const wanted = fresh.some((o) => o.minutes === selectedLate) ? selectedLate : defaultLate(fresh);
    const option = fresh.find((o) => o.minutes === wanted);
    if (!option) {
      setError({ message: t("Your reservation ends soon. There is nothing left to postpone."), login: false });
      return;
    }
    void run("later", new Date(option.until));
  }

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
        <TokenErrorNotice error={blocked} />
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
              {options.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {options.map((o) => (
                    <button
                      key={o.minutes}
                      type="button"
                      aria-pressed={o.minutes === selectedLate}
                      onClick={() => setLateMinutes(o.minutes)}
                      className={`${chipBtn} ${o.minutes === selectedLate ? "!border-brand-500 !bg-brand-100 dark:!bg-brand-900/50" : ""}`}
                    >
                      {lateOptionLabel(o, t, i18n.language)}
                    </button>
                  ))}
                  <button type="button" disabled={busy} onClick={saveLate} className={primaryBtn}>
                    {t("Save")}
                  </button>
                </div>
              )}
              {options.length === 0 && (
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {t("Your reservation ends soon. There is nothing left to postpone.")}
                </p>
              )}
            </>
          )}
          {error && (
            <TokenErrorNotice error={error} className="mt-4" />
          )}
        </>
      )}
      <div className="mt-6 flex flex-wrap gap-2">
        <Link to="/desks/mine" className={linkBtn}>
          {t("My reservations")}
        </Link>
        <Link to="/desks/free" className={linkBtn}>
          {t("Free now")}
        </Link>
      </div>
    </section>
  );
}
