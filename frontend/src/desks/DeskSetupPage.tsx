// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth";
import { SettingsForm } from "./DeskSettingsPage";
import { useDeskPools } from "./pools";
import { inputCls, labelCls } from "./components/formStyles";

/** App admins: switch desksharing on for a pool that doesn't have it yet —
 *  the way into the desk area before the first department exists (and to
 *  further ones). Once saved enabled, the area opens on that department. */
export function DeskSetupPage() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const { select } = useDeskPools();
  const pools = user?.desk_setup_pools ?? [];
  const hasDepartments = (user?.desk_pool_ids?.length ?? 0) > 0;
  const [chosen, setChosen] = useState<number | null>(null);
  const pool = pools.some((p) => p.id === chosen) ? (chosen as number) : (pools[0]?.id ?? null);

  if (pool === null) return <Navigate to="/desks" replace />;

  async function saved(enabled: boolean) {
    if (!enabled || pool === null) return;
    await refresh();
    select(pool);
    navigate("/desks/manage/settings");
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="mb-1 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("Set up desksharing")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {t(
            "Choose a pool and switch desksharing on. The pool needs at least one access group; its members can then book its desks and meeting rooms.",
          )}
        </p>
        {hasDepartments && (
          <p className="mt-2 text-sm">
            <Link to="/desks" className="font-medium text-slate-900 underline underline-offset-2 dark:text-slate-100">
              {t("‹ Back")}
            </Link>
          </p>
        )}
      </div>
      <div>
        <label htmlFor="desk-setup-pool" className={labelCls}>
          {t("Pool")}
        </label>
        <select
          id="desk-setup-pool"
          value={pool}
          onChange={(e) => setChosen(Number(e.target.value))}
          className={inputCls}
        >
          {pools.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <SettingsForm key={pool} pool={pool} onSaved={(s) => void saved(s.enabled)} />
    </div>
  );
}
