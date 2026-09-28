// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RichText } from "@basicbar/ui";
import { api, ApiError } from "../api";
import { Empty, ErrorBox, Loading } from "../components/Status";
import type { PageDetail } from "../types";

/**
 * Public, admin-editable content page (Imprint, Privacy, …), rendered from
 * rich (HTML) text. Reached at "/pages/:slug" and linked from the footer; no sign-in
 * required, so it sits outside the RequireAuth gate. An unknown or unpublished
 * slug answers 404 → we show a friendly "not found", not a raw error.
 */
export function PageView() {
  const { t } = useTranslation();
  const { slug } = useParams();
  const [data, setData] = useState<PageDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotFound(false);
    api
      .getPage(slug!)
      .then((page) => {
        if (!cancelled) setData(page);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setError(err instanceof Error ? err.message : t("Could not load the page."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, t]);

  if (loading) return <Loading />;
  if (notFound) return <Empty label={t("Page not found.")} />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Empty label={t("Page not found.")} />;

  return (
    <article className="pb-10">
      <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {data.title}
      </h1>
      <div className="mt-4 text-slate-800 dark:text-slate-200">
        <RichText html={data.body} />
      </div>
    </article>
  );
}
