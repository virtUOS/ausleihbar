// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";

/** Start-page notice for overdue returns and missed pickups (#133), by the
 *  lending desk's rule. Renders nothing when nothing is overdue. */
export function OverdueNotice({ className = "" }: { className?: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const authed = !!user?.authenticated;
  const { data } = useFetch(
    () => (authed ? api.myOverdueBookings() : Promise.resolve([])),
    [authed],
  );
  const bookings = data ?? [];
  const returns = bookings.reduce((n, b) => n + (b.overdue?.returns ?? 0), 0);
  const pickups = bookings.some((b) => (b.overdue?.pickups ?? 0) > 0);
  if (!returns && !pickups) return null;
  return (
    <div
      role="status"
      className={`flex items-start gap-3 rounded-2xl border-2 border-red-500 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200 ${className}`}
    >
      <TriangleAlert aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
      <div>
        {returns > 0 && (
          <p className="font-semibold">
            {t("You have {{count}} overdue item — please return it as soon as possible.", {
              count: returns,
            })}
          </p>
        )}
        {pickups && (
          <p className={returns > 0 ? "mt-1" : "font-semibold"}>
            {t("You missed a pickup — please contact the lending team.")}
          </p>
        )}
        <Link to="/bookings#overdue" className="mt-1 inline-block font-medium underline">
          {t("Show overdue bookings")}
        </Link>
      </div>
    </div>
  );
}
