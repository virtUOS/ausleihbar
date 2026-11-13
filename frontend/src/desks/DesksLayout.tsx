// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Outlet, useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Armchair } from "lucide-react";
import { useAuth } from "../auth";
import { Empty, Loading } from "../components/Status";
import { DeskTabs } from "./DeskTabs";
import { useDeskPools, type DeskPool } from "./pools";

export interface DesksContext {
  pool: number;
  pools: DeskPool[];
  isAdmin: boolean;
  isAssistant: boolean;
  /** Switch the current department (one of `pools`). */
  select: (id: number) => void;
}

/** Page context of the desksharing area (current department). */
export function useDesks(): DesksContext {
  return useOutletContext<DesksContext>();
}

/** Shell of every `/desks/*` page: menu, department picker, access gate. */
export function DesksLayout() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { pools, current, select, isAdmin, isAssistant } = useDeskPools();
  const hasAccess = (user?.desk_pool_ids?.length ?? 0) > 0;

  if (!hasAccess) {
    return <Empty icon={Armchair} label={t("Desks are not available to you.")} />;
  }
  if (current === null) return <Loading />;

  return (
    <div>
      {/* The visible title is the menu group heading (TabMenu). */}
      <h1 className="sr-only">{t("Desks")}</h1>
      {pools.length > 1 ? (
        <div className="mb-4">
          <label
            htmlFor="desk-pool"
            className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300"
          >
            {t("Department")}
          </label>
          <select
            id="desk-pool"
            value={current}
            onChange={(e) => select(Number(e.target.value))}
            className="min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            {pools.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{pools[0]?.name}</p>
      )}
      <DeskTabs isAdmin={isAdmin} isAssistant={isAssistant} />
      <Outlet context={{ pool: current, pools, isAdmin, isAssistant, select } satisfies DesksContext} />
    </div>
  );
}
