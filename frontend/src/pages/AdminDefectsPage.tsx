// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ExternalLink, Plug } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ManageTabs } from "../components/ManageTabs";
import { ErrorBox, Loading } from "../components/Status";
import type { DefectRow } from "../types";

import { formatDate as fmtDate } from "../dates";

function ProblemCount({ n }: { n: number }) {
  const { t } = useTranslation();
  const tone =
    n >= 3
      ? "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300"
      : n === 2
        ? "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
        : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>
      {t("{{count}}× problem", { count: n })}
    </span>
  );
}

export function AdminDefectsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data, loading, error } = useFetch<{ resources: DefectRow[] }>(
    () => api.getInventoryDefects(),
    [],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const rows = data?.resources ?? [];
  const current = rows.filter((r) => r.currently_defective);
  const past = rows.filter((r) => !r.currently_defective);

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <div className="mb-4 flex justify-end">
        <Link
          to="/manage/defect-tickets"
          className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Plug aria-hidden className="h-4 w-4" />
          {t("Connect GitLab")}
        </Link>
      </div>

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <div className="space-y-6">
          <Section
            title={t("Currently defective ({{count}})", { count: current.length })}
            rows={current}
            showSince
            empty={t("No devices are defective right now. 🎉")}
          />
          <Section
            title={t("Previously defective ({{count}})", { count: past.length })}
            rows={past}
            empty={t("No repaired devices on record.")}
          />
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  rows,
  showSince,
  empty,
}: {
  title: string;
  rows: DefectRow[];
  showSince?: boolean;
  empty: string;
}) {
  const { t } = useTranslation();
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">{empty}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Device")}</th>
                <th className="px-3 py-2">{t("Pool")}</th>
                <th className="px-3 py-2">{showSince ? t("Defective since / note") : t("Last defect")}</th>
                <th className="px-3 py-2">{t("History")}</th>
                <th className="px-3 py-2">{t("Ticket")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2">
                    <Link
                      to={`/manage/inventory/${r.id}`}
                      className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                    >
                      {r.inventory_number}
                    </Link>
                    <span className="text-slate-600 dark:text-slate-300"> · {r.product_title}</span>
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{r.pool_name}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {showSince ? (
                      <>
                        {fmtDate(r.defective_since)}
                        {r.defect_note && (
                          <span className="text-slate-400 dark:text-slate-300"> · {r.defect_note}</span>
                        )}
                      </>
                    ) : (
                      fmtDate(r.last_defect)
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <ProblemCount n={r.defect_count} />
                  </td>
                  <td className="px-3 py-2">
                    {r.gitlab_issue_url ? (
                      <a
                        href={r.gitlab_issue_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-400"
                      >
                        {t("Issue")}
                        <ExternalLink aria-hidden className="h-3.5 w-3.5" />
                      </a>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-300">–</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
