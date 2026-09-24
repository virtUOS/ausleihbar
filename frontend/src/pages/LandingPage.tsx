// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import { useAuth, rememberRedirect } from "../auth";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { symbolFor } from "../emoji";
import type { WelcomeData } from "../types";

/**
 * Public landing page for visitors who are not signed in: a warm honey hero
 * with the admin-defined Markdown welcome text and a prominent sign-in CTA,
 * followed by the lending locations as image-led tiles (one staggered
 * entrance — the page's single choreographed moment). Signed-in users never
 * see this (the shop renders at "/").
 */
export function LandingPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const { data, loading, error } = useFetch<WelcomeData>(() => api.getWelcome(), []);

  return (
    <div className="pb-10">
      <section className="animate-fade-up overflow-hidden rounded-3xl border border-brand-200 bg-brand-100 px-6 py-12 text-center sm:px-10">
        <p className="text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl">
          ausleih<span className="text-brand-800">BAR</span>
        </p>
        {loading && <Loading />}
        {error && <ErrorBox message={error} />}
        {data?.text && (
          <div className="prose prose-slate mx-auto mt-5 max-w-2xl text-left text-slate-800 prose-headings:text-slate-900 prose-a:text-slate-900">
            <ReactMarkdown>{data.text}</ReactMarkdown>
          </div>
        )}
        <button
          type="button"
          onClick={login}
          className="mt-8 rounded-full bg-slate-900 px-7 py-3 text-sm font-bold text-white transition-all duration-150 hover:bg-slate-800 active:scale-[0.98]"
        >
          {t("Sign in to start")}
        </button>
      </section>

      {data && data.pools.length > 0 && (
        <section className="mt-10" aria-labelledby="locations-heading">
          <h2
            id="locations-heading"
            className="mb-4 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100"
          >
            {t("Pools")}
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {data.pools.map((pool, index) => (
              // A pool tile takes the visitor straight to that pool — sign-in is
              // required first, so it returns them there afterwards (#8).
              <button
                key={pool.id}
                type="button"
                onClick={() => {
                  // Return the visitor to this pool after sign-in. login()'s own
                  // rememberRedirect("/") is a no-op, so this target survives.
                  rememberRedirect(`/pools/${pool.id}`);
                  login();
                }}
                aria-label={t("Sign in to view {{name}}", { name: pool.name })}
                className="group animate-fade-up block overflow-hidden rounded-2xl border border-slate-200 bg-white text-left transition-all duration-200 ease-out-quart hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md hover:shadow-slate-900/[0.04] dark:border-slate-800 dark:bg-slate-900"
                style={{ animationDelay: `${Math.min(index * 60, 360)}ms`, animationFillMode: "backwards" }}
              >
                <div className="flex aspect-video items-center justify-center overflow-hidden bg-brand-50 dark:bg-brand-900/30">
                  {pool.image ? (
                    <img
                      src={pool.image}
                      alt=""
                      className="h-full w-full object-cover transition-transform duration-300 ease-out-quart group-hover:scale-[1.04]"
                    />
                  ) : (
                    <span className="text-4xl transition-transform duration-300 ease-out-quart group-hover:scale-110" aria-hidden>
                      {symbolFor(pool.name, pool.room)}
                    </span>
                  )}
                </div>
                <div className="px-4 py-3">
                  <p className="font-bold text-slate-900 dark:text-slate-100">
                    {pool.name}
                    {pool.room ? (
                      <span className="font-normal text-slate-600 dark:text-slate-300"> · {pool.room}</span>
                    ) : null}
                  </p>
                  {pool.description && (
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{pool.description}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
