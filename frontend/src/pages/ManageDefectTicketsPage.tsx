// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ManageTabs } from "../components/ManageTabs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import type { DefectTicketConfig } from "../types";

/** Per-pool GitLab integration: when a device in a pool is marked defective an
 *  issue is opened in the linked project. Opt-in; most pools leave it blank. */
export function ManageDefectTicketsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data, loading, error } = useFetch<DefectTicketConfig[]>(
    () => api.getDefectTickets(),
    [],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Connect GitLab")}</h2>
      <p className="mb-4 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
        {t(
          "When a device in a pool is marked defective, automatically open an issue in the linked GitLab project. Leave the URL blank to disable.",
        )}
      </p>

      <Guide />

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && data.length === 0 && (
        <Empty label={t("You don't manage any pools yet.")} />
      )}
      {data && data.length > 0 && (
        <div className="mt-4 space-y-4">
          {data.map((pool) => (
            <PoolTicketRow key={pool.id} pool={pool} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Short "how to set it up" panel: where to get the token and what to mind. */
function Guide() {
  const { t } = useTranslation();
  return (
    <details className="mb-2 max-w-2xl rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
        {t("How to set this up")}
      </summary>
      <div className="space-y-3 border-t border-slate-100 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-300">
        <div>
          <p className="font-semibold text-slate-800 dark:text-slate-100">{t("Project URL")}</p>
          <p>
            {t(
              "Paste the full URL of the GitLab project that should receive the tickets, including the server, e.g. https://gitlab.example.com/team/devices.",
            )}
          </p>
        </div>
        <div>
          <p className="font-semibold text-slate-800 dark:text-slate-100">{t("Access token")}</p>
          <p>
            {t(
              "In that project open Settings → Access Tokens and create a Project Access Token with the lowest role that can create issues — “Reporter” — and tick only the “api” scope (leave every other scope unchecked; “read_api” is not enough, since creating an issue is a write). Copy the token (GitLab shows it only once) and paste it here.",
            )}
          </p>
        </div>
        <div>
          <p className="font-semibold text-slate-800 dark:text-slate-100">{t("Good to know")}</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>{t("Prefer a project or group token over a personal one, so it isn't tied to a single account.")}</li>
            <li>{t("Give the token an expiry and renew it in time — GitLab will stop accepting an expired token.")}</li>
            <li>{t("The token is stored write-only: it is never shown again here, only whether one is set.")}</li>
            <li>{t("Each created ticket links back here so the device can be returned to service after the repair.")}</li>
          </ul>
        </div>
      </div>
    </details>
  );
}

function PoolTicketRow({ pool }: { pool: DefectTicketConfig }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState(pool.defect_gitlab_url);
  const [token, setToken] = useState("");
  const [tokenSet, setTokenSet] = useState(pool.defect_gitlab_token_set);
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  const inputClass =
    "w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

  async function save(clearToken = false) {
    setStatus("saving");
    setError(null);
    try {
      const body: { defect_gitlab_url: string; defect_gitlab_token?: string } = {
        defect_gitlab_url: url.trim(),
      };
      if (clearToken) body.defect_gitlab_token = "";
      else if (token) body.defect_gitlab_token = token;
      const updated = await api.updateDefectTicket(pool.id, body);
      setTokenSet(updated.defect_gitlab_token_set);
      setToken("");
      setStatus("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("Save failed."));
      setStatus("idle");
    }
  }

  return (
    <div className="max-w-2xl rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">{pool.name}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs text-slate-600 dark:text-slate-300">{t("GitLab project URL")}</span>
          <input
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setStatus("idle");
            }}
            placeholder="https://gitlab.example.com/group/project"
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-600 dark:text-slate-300">{t("Access token")}</span>
          <input
            type="password"
            value={token}
            onChange={(e) => {
              setToken(e.target.value);
              setStatus("idle");
            }}
            placeholder={tokenSet ? t("Stored — leave blank to keep") : t("Personal/project access token")}
            autoComplete="off"
            className={inputClass}
          />
        </label>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => save()}
          disabled={status === "saving"}
          className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-50"
        >
          {status === "saving" ? t("Saving…") : t("Save")}
        </button>
        {tokenSet && (
          <button
            type="button"
            onClick={() => save(true)}
            className="text-xs text-slate-500 hover:text-red-600 dark:text-slate-300"
          >
            {t("Remove token")}
          </button>
        )}
        {status === "saved" && (
          <span className="text-xs text-emerald-600 dark:text-emerald-400">{t("Saved")}</span>
        )}
        {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
      </div>
    </div>
  );
}
