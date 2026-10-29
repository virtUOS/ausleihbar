// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AccessGroupMember } from "../types";

/** Small neutral tag next to a member ("manuell", "automatisch", …). */
export const memberChipClass =
  "inline-block rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs text-slate-700 dark:text-slate-200";

/**
 * The effective members of an access group, one per line: name, e-mail, an
 * optional tag (`tag(m)`) and "deaktiviert" for inactive accounts. With
 * `onRemove`, members for which `canRemove(m)` holds get a ✕ button (#171).
 */
export function AccessGroupMemberList({
  members,
  tag,
  canRemove,
  onRemove,
  busyId,
  scroll = true,
}: {
  members: AccessGroupMember[];
  tag?: (m: AccessGroupMember) => ReactNode;
  canRemove?: (m: AccessGroupMember) => boolean;
  onRemove?: (m: AccessGroupMember) => void;
  /** Member whose removal is in flight (its button is disabled). */
  busyId?: number | null;
  /** Cap the height and scroll (the compact admin table cell). */
  scroll?: boolean;
}) {
  const { t } = useTranslation();
  if (members.length === 0)
    return <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">–</p>;
  return (
    <ul className={`mt-1 space-y-1 ${scroll ? "max-h-48 overflow-y-auto" : ""}`}>
      {members.map((m) => {
        const label = m.name || m.username;
        return (
          <li
            key={m.id}
            className={`flex flex-wrap items-center gap-2 text-xs ${
              m.is_active
                ? "text-slate-700 dark:text-slate-200"
                : "text-slate-600 dark:text-slate-300"
            }`}
          >
            <span>{label}</span>
            {m.email && <span className="text-slate-500 dark:text-slate-400">{m.email}</span>}
            {tag?.(m)}
            {!m.is_active && <span className={memberChipClass}>{t("deactivated")}</span>}
            {onRemove && (canRemove ? canRemove(m) : true) && (
              <button
                type="button"
                onClick={() => onRemove(m)}
                disabled={busyId === m.id}
                aria-label={t("Remove {{name}}", { name: label })}
                title={t("Remove {{name}}", { name: label })}
                className="inline-flex h-6 w-6 items-center justify-center rounded-full text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-red-700 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-red-300"
              >
                <X aria-hidden className="h-3.5 w-3.5" />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
