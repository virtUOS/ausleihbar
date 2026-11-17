// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatDayWithWeekday } from "../../dates";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { pad2 } from "../weekdays";
import type { DeskRequest, RequestBrief } from "../types";

const btn =
  "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";
const btnPrimary =
  "min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 hover:bg-brand-400 disabled:opacity-50";
const incomingCard =
  "rounded-xl border border-brand-300 bg-brand-50 p-3 dark:border-brand-700/60 dark:bg-brand-900/20";
const outgoingCard = "rounded-xl border border-slate-200 p-3 dark:border-slate-800";

/** A batch of release requests (sent together, e.g. from the booking page),
 *  or a single request that renders as before (swaps, legacy releases). */
type Group =
  | { kind: "batch"; batch: string; rows: DeskRequest[] }
  | { kind: "single"; req: DeskRequest };

function groupRequests(rows: DeskRequest[]): Group[] {
  const groups: Group[] = [];
  const byBatch = new Map<string, DeskRequest[]>();
  for (const req of rows) {
    if (req.type === "release" && req.batch) {
      let list = byBatch.get(req.batch);
      if (!list) {
        list = [];
        byBatch.set(req.batch, list);
        groups.push({ kind: "batch", batch: req.batch, rows: list });
      }
      list.push(req);
    } else {
      groups.push({ kind: "single", req });
    }
  }
  for (const list of byBatch.values()) {
    list.sort((a, b) => {
      const da = slot(a, a.own ?? a.other);
      const db = slot(b, b.own ?? b.other);
      return da.day.localeCompare(db.day) || da.start_hour - db.start_hour;
    });
  }
  return groups;
}

/** Day and hours a release request is about: the wanted hours, else the
 *  reservation's own. */
function slot(req: DeskRequest, brief?: RequestBrief) {
  return req.wanted ?? { day: brief?.day ?? "", start_hour: brief?.start_hour ?? 0, end_hour: brief?.end_hour ?? 0 };
}

/** True when only part of the reservation is asked for (the whole one is
 *  released on acceptance). */
function partOf(req: DeskRequest, brief: RequestBrief) {
  return !!req.wanted && (req.wanted.start_hour !== brief.start_hour || req.wanted.end_hour !== brief.end_hour);
}

/** Open swap and release requests in "Meine Buchungen". Release requests of
 *  one batch share a card with per-date and "all" actions. */
export function MyRequests({
  incoming,
  outgoing,
  onChanged,
}: {
  incoming: DeskRequest[];
  outgoing: DeskRequest[];
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);

  const when = (b?: RequestBrief) =>
    b ? `${b.place.name}, ${formatDayWithWeekday(b.day)} ${pad2(b.start_hour)}:00–${pad2(b.end_hour)}:00` : "";
  const wantedWhen = (req: DeskRequest, b?: RequestBrief) => {
    const s = slot(req, b);
    return `${b?.place.name ?? ""}, ${formatDayWithWeekday(s.day)} ${pad2(s.start_hour)}:00–${pad2(s.end_hour)}:00`;
  };

  async function answer(req: DeskRequest, accept: boolean) {
    setBusy(true);
    try {
      if (req.type === "swap") await desksApi.answerSwap(req.id, accept);
      else await desksApi.answerRelease(req.id, accept);
      toast.success(accept ? t("Request accepted.") : t("Request declined."));
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      // A failed handover expires the request: show the current state.
      if (req.type === "release") onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function answerAll(batch: string, rows: DeskRequest[], accept: boolean) {
    if (
      accept &&
      !(await confirm({
        title: t("Accept all requests?"),
        message: t("Your bookings on these days are released completely and the listed times go to the person asking. This cannot be undone."),
        confirmLabel: t("Accept all"),
      }))
    )
      return;
    setBusy(true);
    try {
      const { done, failed } = await desksApi.answerReleaseBatch(batch, accept);
      if (done.length) toast.success(accept ? t("Request accepted.") : t("Request declined."));
      if (failed.length) {
        const dates = rows
          .filter((r) => failed.includes(r.id))
          .map((r) => wantedWhen(r, r.own))
          .join("; ");
        toast.warning(
          dates
            ? t("Not completed, nothing was changed for: {{dates}}", { dates })
            : t("The request could not be completed. Nothing was changed."),
        );
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function withdraw(req: DeskRequest) {
    setBusy(true);
    try {
      await desksApi.withdrawRelease(req.id);
      toast.success(t("Request withdrawn."));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function withdrawAll(batch: string) {
    if (
      !(await confirm({
        title: t("Withdraw all requests?"),
        message: t("All open requests for the listed times are withdrawn."),
        confirmLabel: t("Withdraw all"),
        cancelLabel: t("Keep"),
      }))
    )
      return;
    setBusy(true);
    try {
      await desksApi.withdrawReleaseBatch(batch);
      toast.success(t("Request withdrawn."));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  function incomingText(req: DeskRequest) {
    if (req.type === "swap") {
      return t("Someone asks to swap: you give {{own}} and get {{other}}.", {
        own: when(req.own),
        other: when(req.other),
      });
    }
    return req.requester_name
      ? t("{{name}} asks you to release {{own}}.", { name: req.requester_name, own: when(req.own) })
      : t("Someone asks you to release {{own}}.", { own: when(req.own) });
  }

  function outgoingText(req: DeskRequest) {
    const who = req.other_holder_name ?? t("Person (hidden)");
    return req.type === "swap"
      ? t("Waiting for {{name}}: swap with {{other}}.", { name: who, other: when(req.other) })
      : t("Waiting for {{name}}: release of {{other}}.", { name: who, other: when(req.other) });
  }

  return (
    <div className="mb-6 space-y-2">
      <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">{t("Requests")}</h3>
      {groupRequests(incoming).map((g) =>
        g.kind === "single" ? (
          <div key={`in-${g.req.type}-${g.req.id}`} className={incomingCard}>
            <p className="text-sm text-slate-900 dark:text-slate-100">{incomingText(g.req)}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={() => answer(g.req, true)} className={btnPrimary}>
                {t("Accept")}
              </button>
              <button type="button" disabled={busy} onClick={() => answer(g.req, false)} className={btn}>
                {t("Decline")}
              </button>
            </div>
          </div>
        ) : (
          <div key={`in-batch-${g.batch}`} className={incomingCard}>
            <p className="text-sm text-slate-900 dark:text-slate-100">
              {t("{{name}} asks you to release these times:", {
                name: g.rows[0].requester_name || t("Someone"),
              })}
            </p>
            <ul className="mt-2 divide-y divide-brand-200 dark:divide-brand-800/60">
              {g.rows.map((req) => (
                <li key={req.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="text-sm text-slate-900 dark:text-slate-100">
                    {wantedWhen(req, req.own)}
                    {req.own && partOf(req, req.own) && (
                      <span className="block text-xs text-slate-600 dark:text-slate-300">
                        {t("Your booking ({{hours}}) is released completely.", {
                          hours: `${pad2(req.own.start_hour)}:00–${pad2(req.own.end_hour)}:00`,
                        })}
                      </span>
                    )}
                  </span>
                  <span className="flex flex-wrap gap-2">
                    <button type="button" disabled={busy} onClick={() => answer(req, true)} className={btnPrimary}>
                      {t("Accept")}
                    </button>
                    <button type="button" disabled={busy} onClick={() => answer(req, false)} className={btn}>
                      {t("Decline")}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
            {g.rows.length > 1 && (
              <div className="mt-2 flex flex-wrap gap-2 border-t border-brand-200 pt-3 dark:border-brand-800/60">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => answerAll(g.batch, g.rows, true)}
                  className={btnPrimary}
                >
                  {t("Accept all")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => answerAll(g.batch, g.rows, false)}
                  className={btn}
                >
                  {t("Decline all")}
                </button>
              </div>
            )}
          </div>
        ),
      )}
      {groupRequests(outgoing).map((g) =>
        g.kind === "single" ? (
          <p
            key={`out-${g.req.type}-${g.req.id}`}
            className={`${outgoingCard} text-sm text-slate-700 dark:text-slate-200`}
          >
            {outgoingText(g.req)}
          </p>
        ) : (
          <div key={`out-batch-${g.batch}`} className={outgoingCard}>
            <p className="text-sm text-slate-700 dark:text-slate-200">{t("Waiting for answers: release of these times:")}</p>
            <ul className="mt-2 divide-y divide-slate-200 dark:divide-slate-800">
              {g.rows.map((req) => (
                <li key={req.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="text-sm text-slate-700 dark:text-slate-200">
                    {wantedWhen(req, req.other)}
                    {req.other_holder_name && (
                      <span className="text-slate-600 dark:text-slate-300"> · {req.other_holder_name}</span>
                    )}
                  </span>
                  <button type="button" disabled={busy} onClick={() => withdraw(req)} className={btn}>
                    {t("Withdraw")}
                  </button>
                </li>
              ))}
            </ul>
            {g.rows.length > 1 && (
              <div className="mt-2 border-t border-slate-200 pt-3 dark:border-slate-800">
                <button type="button" disabled={busy} onClick={() => withdrawAll(g.batch)} className={btn}>
                  {t("Withdraw all")}
                </button>
              </div>
            )}
          </div>
        ),
      )}
    </div>
  );
}
