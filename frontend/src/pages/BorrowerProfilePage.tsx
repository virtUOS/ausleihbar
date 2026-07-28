// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { ManageTabs } from "../components/ManageTabs";
import { UserBookingHistory } from "../components/UserBookingHistory";
import type { BorrowerProfile } from "../types";

function fmtDate(iso: string | null): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Read-only borrower profile reachable from the lending desk by clicking a
 *  borrower's name. Lenders can issue a strike here; deleting strikes and
 *  unblocking stay with admins under Administration → Users. */
export function BorrowerProfilePage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = Number(id);
  const [version, setVersion] = useState(0);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { data, loading, error } = useFetch<BorrowerProfile>(
    () => api.getBorrowerProfile(userId),
    [userId, version],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  async function addStrike(event: React.FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.createStrike({ user: userId, reason: reason.trim() });
      setReason("");
      setVersion((v) => v + 1);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t("Action failed."));
    } finally {
      setBusy(false);
    }
  }

  const blockLabel = data?.blocked_permanently
    ? t("Blocked indefinitely")
    : data?.blocked_until
      ? t("Blocked until {{date}}", { date: fmtDate(data.blocked_until) })
      : null;

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 text-sm text-slate-500 hover:underline dark:text-slate-400"
      >
        ‹ {t("Back")}
      </button>

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <div className="space-y-5">
          <header className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {data.full_name || data.username}
            </h2>
            <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
              {data.username}
              {data.email && <> · {data.email}</>}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              {data.is_blocked ? (
                <span className="rounded-full bg-red-600 px-2 py-0.5 font-semibold text-white">
                  {blockLabel}
                </span>
              ) : (
                <span className="text-slate-500 dark:text-slate-400">
                  {t("Not blocked")} ·{" "}
                  {t("{{count}} active strike", { count: data.active_strikes })}
                </span>
              )}
            </div>
          </header>

          <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Strikes")}</h3>
            {data.strikes.length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-slate-500">{t("No strikes.")}</p>
            ) : (
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
                {data.strikes.map((s) => (
                  <li key={s.id} className="px-3 py-2 text-sm">
                    <p className="text-slate-800 dark:text-slate-200">{s.reason}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">
                      {fmtDate(s.created_at)}
                      {s.issued_by && ` · ${t("by {{name}}", { name: s.issued_by })}`} ·{" "}
                      {s.is_active
                        ? t("active until {{date}}", { date: fmtDate(s.expires_at) })
                        : t("expired")}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            <form onSubmit={addStrike} className="mt-3 flex gap-2">
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t("Reason for a new strike…")}
                className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
              />
              <button
                type="submit"
                disabled={busy || !reason.trim()}
                className="rounded-full bg-brand-400 px-3 py-1 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
              >
                {t("Add strike")}
              </button>
            </form>
            {formError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{formError}</p>}
            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
              {t("Removing strikes or unblocking is done by admins under Administration → Users.")}
            </p>
          </section>

          <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
              {t("Booking history")}
            </h3>
            <UserBookingHistory userId={userId} getBookings={api.getBorrowerBookings} />
          </section>
        </div>
      )}
    </div>
  );
}
