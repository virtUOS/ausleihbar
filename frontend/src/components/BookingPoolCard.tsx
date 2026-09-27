// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Clock, MapPin } from "lucide-react";
import { poolAccent } from "../poolAccent";
import { poolHoursCompact } from "../pools";
import type { BookingTone } from "../bookingStatus";
import type { BookingPool } from "../types";

/** One reservation in the cart's visual language (#37): a pool-coloured strip
 *  and header (pickup location, optionally address + opening hours) framing
 *  the card body. The tone makes the status visible at a glance. */
export function BookingPoolCard({
  pool,
  tone,
  details,
  className = "",
  children,
}: {
  pool: BookingPool | null | undefined;
  tone: BookingTone;
  details: boolean;
  /** Border colour classes for the outer frame, replacing the default
   *  slate border (e.g. a strike's red border). */
  className?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const accent = poolAccent(pool?.accent_color);
  const done = tone === "done";
  const strip =
    tone === "active"
      ? `w-1.5 ${accent.bar}`
      : tone === "pending"
        ? `border-l-4 border-dashed ${accent.border}`
        : "w-1.5 bg-slate-500 dark:bg-slate-600";
  const head =
    tone === "active" ? accent.tint : tone === "pending" ? accent.tintSoft : "bg-slate-100 dark:bg-slate-800";
  const pin = done ? "text-slate-500 dark:text-slate-400" : accent.text;
  const hours = pool && details ? poolHoursCompact(pool.opening_hours, pool.closed_weekdays) : [];

  return (
    <div className={`flex overflow-hidden rounded-xl border bg-white dark:bg-slate-900 ${className || "border-slate-200 dark:border-slate-800"}`}>
      <div aria-hidden className={`shrink-0 ${strip}`} />
      <div className="min-w-0 flex-1">
        {pool && (
          <div className={`border-b border-slate-100 px-4 py-2.5 text-sm dark:border-slate-800 ${head}`}>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <MapPin aria-hidden className={`h-4 w-4 shrink-0 ${pin}`} />
              <Link
                to={`/pools/${pool.id}`}
                className="font-semibold text-slate-900 hover:underline dark:text-slate-100"
              >
                {pool.name}
              </Link>
              {pool.room && <span className="text-slate-600 dark:text-slate-300">· {pool.room}</span>}
            </p>
            {details && pool.address && (
              <p className="mt-1 whitespace-pre-line pl-6 text-slate-700 dark:text-slate-200">{pool.address}</p>
            )}
            {details && hours.length > 0 && (
              <div className="mt-1 flex items-start gap-2 pl-6 text-slate-700 dark:text-slate-200">
                <Clock aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500 dark:text-slate-400" />
                <span>
                  <span className="sr-only">{t("Service times")}: </span>
                  {hours.map((d) => `${d.label} ${d.ranges.join(", ")}`).join(" · ")}
                </span>
              </div>
            )}
          </div>
        )}
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
