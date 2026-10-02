// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth";
import {
  setPoolScope,
  usePoolScope,
  usePoolScopeLocked,
  type PoolScope,
} from "../poolScope";

// Switching the scope remounts the lending page (App keys its routes by the
// scope), which would drop keyboard focus to <body>. Remember that the switch
// was just used so the freshly mounted switch can take focus back.
let refocusAfterSwitch = false;

/**
 * "My pools (n) | All pools" — the lending-area pool scope for admins who are
 * also assigned as lenders (`whoami.lending_scope_pool_ids`). Renders nothing
 * for everyone else. A view filter only: "All pools" is the support view.
 */
export function PoolScopeSwitch() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const scope = usePoolScope();
  const locked = usePoolScopeLocked();
  const hintId = useId();
  const mineRef = useRef<HTMLButtonElement>(null);
  const allRef = useRef<HTMLButtonElement>(null);

  const own = user?.lending_scope_pool_ids;
  const visible = Array.isArray(own) && own.length > 0;

  useEffect(() => {
    if (!visible || !refocusAfterSwitch) return;
    refocusAfterSwitch = false;
    (scope === "all" ? allRef : mineRef).current?.focus();
  }, [visible, scope]);

  if (!visible) return null;

  const lockHint = t("Finish or clear the walk-in first");
  const choose = (next: PoolScope) => {
    if (next === scope || locked) return;
    refocusAfterSwitch = true;
    setPoolScope(next);
  };

  const base =
    "rounded-full px-2.5 py-1 text-xs font-semibold transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed";
  const cls = (on: boolean) =>
    `${base} ${
      on
        ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
        : "text-slate-500 enabled:hover:text-slate-900 dark:text-slate-300 dark:enabled:hover:text-slate-100"
    }`;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <div
        role="group"
        aria-label={t("Pool scope")}
        className="inline-flex gap-0.5 rounded-full bg-slate-100 p-0.5 dark:bg-slate-800"
      >
        <button
          ref={mineRef}
          type="button"
          onClick={() => choose("mine")}
          aria-pressed={scope === "mine"}
          disabled={locked && scope !== "mine"}
          aria-describedby={locked ? hintId : undefined}
          title={locked ? lockHint : undefined}
          className={cls(scope === "mine")}
        >
          {t("My pools ({{n}})", { n: own.length })}
        </button>
        <button
          ref={allRef}
          type="button"
          onClick={() => choose("all")}
          aria-pressed={scope === "all"}
          disabled={locked && scope !== "all"}
          aria-describedby={locked ? hintId : undefined}
          title={locked ? lockHint : undefined}
          className={cls(scope === "all")}
        >
          {t("All pools")}
        </button>
      </div>
      {locked && (
        <span id={hintId} className="text-xs text-slate-500 dark:text-slate-400">
          {lockHint}
        </span>
      )}
      {scope === "all" && (
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
          {t("Support view: all pools")}
        </span>
      )}
    </div>
  );
}
