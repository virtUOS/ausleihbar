// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { DeleteButton } from "./RowActions";
import { useConfirm } from "./ConfirmDialog";
import type { ManageUser } from "../types";

import { formatDate as fmtDate } from "../dates";

/** Admin view of a user's strikes and suspension, with issue/delete/unblock. */
export function UserStrikes({ user }: { user: ManageUser }) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const [data, setData] = useState<ManageUser>(user);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setData(await api.getUser(user.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Action failed."));
    } finally {
      setBusy(false);
    }
  }

  function addStrike(event: React.FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    run(async () => {
      await api.createStrike({ user: user.id, reason: reason.trim() });
      setReason("");
    });
  }

  const blockLabel = data.blocked_permanently
    ? t("Blocked indefinitely")
    : data.blocked_until
      ? t("Blocked until {{date}}", { date: fmtDate(data.blocked_until) })
      : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {data.is_blocked ? (
          <>
            <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white">
              {blockLabel}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => api.unblockUser(user.id))}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {t("Unblock")}
            </button>
          </>
        ) : (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {t("Not blocked")} ·{" "}
            {t("{{count}} active strike", { count: data.active_strikes })}
          </span>
        )}
      </div>

      {data.strikes.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-400">{t("No strikes.")}</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {data.strikes.map((s) => (
            <li key={s.id} className="flex items-start justify-between gap-3 px-3 py-2">
              <div className="min-w-0 text-sm">
                <p className="text-slate-800 dark:text-slate-200">{s.reason}</p>
                <p className="text-xs text-slate-400 dark:text-slate-400">
                  {fmtDate(s.created_at)}
                  {s.issued_by && ` · ${t("by {{name}}", { name: s.issued_by })}`} ·{" "}
                  {s.is_active
                    ? t("active until {{date}}", { date: fmtDate(s.expires_at) })
                    : t("expired")}
                </p>
              </div>
              <DeleteButton
                onClick={async () => {
                  if (
                    await confirm({
                      message: t("Delete this strike?"),
                      confirmLabel: t("Delete"),
                      danger: true,
                    })
                  )
                    run(() => api.deleteStrike(s.id));
                }}
                disabled={busy}
                className="shrink-0"
              />
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
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-300">{error}</p>}
    </div>
  );
}
