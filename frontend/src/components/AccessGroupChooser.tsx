// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AccessGroup } from "../types";

/** A searchable checkbox list of access groups. The labels default to pool
 *  visibility (#138: the groups whose members may see and book a pool, saved
 *  with the pool form); other choosers (e.g. the department assignment of
 *  desk rooms and places) pass their own `label` / `description` /
 *  `emptyLabel`. The groups themselves (members, claim rules) are managed on
 *  their own page, opened in a new tab so the form keeps its unsaved
 *  changes. */
export function AccessGroupChooser({
  groups,
  error,
  selected,
  onChange,
  label,
  description,
  emptyLabel,
  restricted = false,
}: {
  groups: AccessGroup[] | null;
  error?: string | null;
  selected: number[];
  onChange: (ids: number[]) => void;
  /** Heading; defaults to "Visibility". */
  label?: string;
  /** Line under the heading; defaults to the pool-visibility explanation. */
  description?: string;
  /** Text when there are no groups to choose; defaults to "No access groups defined yet." */
  emptyLabel?: string;
  /** Pool visibility: restricted even without a selected group (a personal
   *  pool, LTI course pools) — never claim "visible to everyone" then. */
  restricted?: boolean;
}) {
  const { t } = useTranslation();
  const headingId = useId();
  const [query, setQuery] = useState("");
  const chosen = new Set(selected);
  const q = query.trim().toLowerCase();
  const visible = (groups ?? []).filter((g) => !q || g.name.toLowerCase().includes(q));

  function toggle(id: number) {
    onChange(chosen.has(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }

  const allUsers = (groups ?? []).find((g) => g.system_all);

  function describe(g: AccessGroup) {
    if (g.system_all) return t("All signed-in people are members automatically.");
    const parts: string[] = [];
    if (g.claim_key) {
      parts.push(`${t("claim")}: ${g.claim_key} ∈ {${g.claim_values.join(", ")}}`);
    }
    parts.push(t("{{count}} manual member", { count: g.member_count }));
    return parts.join(" · ");
  }

  return (
    <div>
      <h5 id={headingId} className="mb-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
        {label ?? t("Visibility")}
      </h5>
      <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">
        {description ??
          (allUsers && chosen.has(allUsers.id)
            ? t("Visible to everyone signed in.")
            : restricted
              ? t("Personal pool: visible to members of linked courses and of the selected groups (plus this pool's lenders and admins).")
              : t("Visible to members of the selected groups (plus this pool's lenders and admins)."))}
      </p>
      {description === undefined && !restricted && allUsers && !chosen.has(allUsers.id) && (
        <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
          {t("Without “All signed-in people” only members of the selected groups see this pool.")}
        </p>
      )}
      {error ? (
        <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
      ) : groups === null ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("Loading…")}</p>
      ) : groups.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">{emptyLabel ?? t("No access groups defined yet.")}</p>
      ) : (
        <>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("Search groups…")}
            aria-label={t("Search groups…")}
            className="mb-2 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 sm:max-w-xs"
          />
          <ul
            aria-labelledby={headingId}
            className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 dark:border-slate-800"
          >
            {visible.map((g) => (
              <li key={g.id}>
                <label className="flex cursor-pointer items-start gap-2 rounded px-1 py-0.5 hover:bg-slate-50 dark:hover:bg-slate-800/60">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={chosen.has(g.id)}
                    onChange={() => toggle(g.id)}
                  />
                  <span>
                    <span className="text-sm font-medium text-slate-800 dark:text-slate-100">{g.name}</span>
                    <span className="block text-xs text-slate-600 dark:text-slate-300">{describe(g)}</span>
                  </span>
                </label>
              </li>
            ))}
            {visible.length === 0 && (
              <li className="px-1 text-sm text-slate-600 dark:text-slate-300">{t("No matches.")}</li>
            )}
          </ul>
        </>
      )}
      <a
        href="/admin/access-groups"
        target="_blank"
        rel="noopener"
        className="mt-1 inline-block text-xs font-medium text-brand-700 hover:underline dark:text-brand-300"
      >
        {t("Manage access groups (new tab) →")}
      </a>
    </div>
  );
}
