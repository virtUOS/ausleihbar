// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Handshake, Settings } from "lucide-react";
import { useAuth } from "../auth";
import { getLastAdminPath } from "../lastAdminPath";
import { AREAS, useAppFunctions, type AppFn, type Area } from "../appFunctions";

const AREA_META: Record<Area, { title: string; icon: typeof Handshake }> = {
  lending: { title: "Lending desk", icon: Handshake },
  admin: { title: "Administration", icon: Settings },
};

/** Glossary / overview of all management functions, split into the two menu
 *  areas and their groups (in menu order), each linking to its page (issues
 *  #28, #97). Role-filtered like the quick search. */
export function AdminFunctionsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const functions = useAppFunctions();

  if (user && !user.is_lender && !user.is_staff) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">
        {t("Not authorized.")}
      </div>
    );
  }

  function goBack() {
    if (location.key !== "default") navigate(-1);
    else navigate(user?.is_lender ? "/manage" : getLastAdminPath());
  }

  // The registry is in menu order, so first-seen order of groups is the menu's.
  const areas = AREAS.map((area) => {
    const groups: { name: string; items: AppFn[] }[] = [];
    for (const fn of functions.filter((f) => f.area === area)) {
      let group = groups.find((g) => g.name === fn.group);
      if (!group) {
        group = { name: fn.group, items: [] };
        groups.push(group);
      }
      group.items.push(fn);
    }
    return { area, groups };
  }).filter((a) => a.groups.length > 0);

  return (
    <div>
      <button
        type="button"
        onClick={goBack}
        className="mb-3 text-sm font-medium text-slate-600 underline-offset-2 hover:underline dark:text-slate-300"
      >
        {t("‹ Back")}
      </button>
      <h1 className="mb-1 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Functions")}
      </h1>
      <p className="mb-4 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
        {t(
          "Every management function you can access, with a short description. Use the search button in the header to jump to any of them quickly.",
        )}
      </p>

      {areas.length > 1 && (
        <nav aria-label={t("On this page")} className="mb-6 flex flex-wrap gap-2">
          {areas.map(({ area }) => {
            const { title, icon: Icon } = AREA_META[area];
            return (
              <a
                key={area}
                href={`#functions-${area}`}
                onClick={(e) => {
                  e.preventDefault();
                  const el = document.getElementById(`functions-${area}`);
                  el?.scrollIntoView({ block: "start" });
                  el?.focus({ preventScroll: true });
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 text-sm font-medium text-slate-700 hover:border-brand-400 hover:bg-brand-50 dark:border-slate-700 dark:text-slate-200 dark:hover:border-brand-400/60 dark:hover:bg-slate-800/50"
              >
                <Icon aria-hidden className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                {t(title)}
              </a>
            );
          })}
        </nav>
      )}

      <div className="space-y-10">
        {areas.map(({ area, groups }) => {
          const { title, icon: Icon } = AREA_META[area];
          return (
            <section key={area} aria-labelledby={`functions-${area}`}>
              <h2
                id={`functions-${area}`}
                tabIndex={-1}
                className="mb-4 flex scroll-mt-4 items-center gap-2 border-b border-slate-200 pb-2 text-lg font-semibold tracking-tight text-slate-900 outline-none dark:border-slate-800 dark:text-slate-100"
              >
                <Icon aria-hidden className="h-5 w-5 text-brand-600 dark:text-brand-400" />
                {t(title)}
              </h2>
              <div className="space-y-6">
                {groups.map((group) => (
                  <section key={group.name}>
                    <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {group.name}
                    </h3>
                    <ul className="grid gap-2 sm:grid-cols-2">
                      {group.items.map((fn) => (
                        <li key={fn.to}>
                          <Link
                            to={fn.to}
                            className="block h-full rounded-lg border border-slate-200 p-3 transition-colors hover:border-brand-400 hover:bg-slate-50 dark:border-slate-800 dark:hover:border-brand-400/60 dark:hover:bg-slate-800/50"
                          >
                            <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                              {fn.label}
                            </span>
                            <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-300">
                              {fn.description}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
