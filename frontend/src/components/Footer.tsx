// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useFetch } from "../useFetch";
import type { PageLink } from "../types";

/**
 * Site footer with admin-configurable links to content pages (Imprint,
 * Privacy, …). The links come from the published, footer-flagged pages; if
 * there are none the footer still shows the credit line. Public — it renders
 * on the landing page too.
 */
export function Footer() {
  const { t } = useTranslation();
  const { data } = useFetch<PageLink[]>(() => api.getFooterPages(), []);
  const links = data ?? [];

  return (
    <footer className="mt-auto border-t border-slate-200 print:hidden dark:border-slate-800">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-2 px-4 py-6 text-sm text-slate-500 sm:flex-row sm:justify-between dark:text-slate-300">
        <p>
          ausleih<span className="font-semibold">BAR</span>
        </p>
        {links.length > 0 && (
          <nav aria-label={t("Footer")}>
            <ul className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
              {links.map((page) => (
                <li key={page.slug}>
                  <Link
                    to={`/pages/${page.slug}`}
                    className="underline-offset-2 hover:text-slate-700 hover:underline dark:hover:text-slate-200"
                  >
                    {page.title}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </div>
    </footer>
  );
}
