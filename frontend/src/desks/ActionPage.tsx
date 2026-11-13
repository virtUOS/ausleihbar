// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck } from "lucide-react";
import { ApiError } from "../api";
import { formatDayWithWeekday, formatTime } from "../dates";
import { desksApi } from "./api";
import type { DeskAction, Reservation } from "./types";

const linkBtn =
  "inline-flex min-h-[44px] items-center justify-center rounded-full border border-slate-300 px-5 text-sm font-semibold text-slate-800 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-800";
const primaryBtn =
  "min-h-[44px] rounded-full bg-brand-500 px-5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50";

/** The reservation id inside the signed action token (its payload is not
 *  secret, only signed). Best effort: used just to show context and cap the
 *  "later" choices; the server decides everything. */
async function reservationIdOf(token: string): Promise<number | null> {
  try {
    let payload = token.split(":")[0];
    const compressed = payload.startsWith(".");
    if (compressed) payload = payload.slice(1);
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4)), (c) => c.charCodeAt(0));
    let text: string;
    if (compressed) {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
      text = await new Response(stream).text();
    } else {
      text = new TextDecoder().decode(bytes);
    }
    const id = Number(JSON.parse(text).r);
    return Number.isInteger(id) ? id : null;
  } catch {
    return null;
  }
}

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
  const [reservation, setReservation] = useState<Reservation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const id = await reservationIdOf(token);
      if (id === null) return;
      try {
        const mine = await desksApi.myReservations();
        if (!cancelled) setReservation(mine.find((r) => r.id === id) ?? null);
      } catch {
        /* context is optional */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  function describe(e: unknown): string {
    if (e instanceof ApiError) {
      if (e.status === 403) return t("This link belongs to another account. Please sign in with the account that received the mail.");
      if (e.status === 410) return t("This link has expired because the reservation is over.");
      const code = (e.data as { code?: string } | undefined)?.code;
      if (code === "already_released") return t("The reservation was already released.");
      if (e.status === 404) return t("The reservation no longer exists.");
      if (code === "invalid_token") return t("This link is invalid.");
    }
    return e instanceof Error ? e.message : t("The request failed.");
  }

  async function run(act: DeskAction, until?: Date) {
    setBusy(true);
    setError(null);
    try {
      await desksApi.action(token, act, until?.toISOString());
      setDone(
        act === "release"
          ? t("The place is released.")
          : t("Noted. Your place stays reserved until {{time}}.", { time: formatTime(until!.toISOString()) }),
      );
    } catch (e) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  const where = reservation
    ? `${reservation.place.name} · ${formatDayWithWeekday(reservation.day)} · ${formatTime(reservation.start)}–${formatTime(reservation.end)}`
    : null;
  const end = reservation ? new Date(reservation.end).getTime() : Infinity;
  const now = Date.now();
  const chips = CHIPS.filter((c) => now + c.minutes * 60_000 < end);

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
                    onClick={() => run("later", new Date(Date.now() + c.minutes * 60_000))}
                    className={primaryBtn}
                  >
                    {c.label}
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
