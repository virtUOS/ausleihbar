// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth";
import { useAppFunctions, type AppFn } from "../appFunctions";

/** Glossary / overview of all management functions, grouped, each linking to
 *  its page (issue #28). Role-filtered like the quick search. */
export function AdminFunctionsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const functions = useAppFunctions();

  if (user && !user.is_lender && !user.is_staff) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">
        {t("Not authorized.")}
      </div>
    );
  }

  // Preserve the registry's group order.
  const groups: { name: string; items: AppFn[] }[] = [];
  for (const fn of functions) {
    let group = groups.find((g) => g.name === fn.group);
    if (!group) {
      group = { name: fn.group, items: [] };
      groups.push(group);
    }
    group.items.push(fn);
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Functions")}
      </h1>
      <p className="mb-5 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
        {t(
          "Every management function you can access, with a short description. Use the search button in the header to jump to any of them quickly.",
        )}
      </p>

      <div className="space-y-6">
        {groups.map((group) => (
          <section key={group.name}>
            <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              {group.name}
            </h2>
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
    </div>
  );
}
