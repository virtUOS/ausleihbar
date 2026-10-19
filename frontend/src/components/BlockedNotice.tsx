// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { formatDate } from "../dates";
import type { WhoAmI } from "../types";

/** Whether the signed-in user is currently blocked from new bookings (strike
 *  suspension). `blocked_until` is null once a block has expired. */
export function isAccountBlocked(user: WhoAmI | null | undefined): boolean {
  if (!user?.authenticated) return false;
  if (user.blocked_permanently) return true;
  return !!user.blocked_until && new Date(user.blocked_until).getTime() > Date.now();
}

export function useAccountBlocked(): boolean {
  const { user } = useAuth();
  return isAccountBlocked(user);
}

/** True for the API's "account blocked" 403 (`code: account_blocked`). */
export function isAccountBlockedError(err: unknown): boolean {
  const data = (err as { status?: number; data?: unknown } | null)?.data;
  return (
    (err as { status?: number } | null)?.status === 403 &&
    (data as { code?: string } | null)?.code === "account_blocked"
  );
}

/** Short visible reason shown next to disabled booking buttons. */
export function BlockedHint({ id, className = "" }: { id: string; className?: string }) {
  const { t } = useTranslation();
  return (
    <p id={id} className={`text-sm text-amber-800 dark:text-amber-200 ${className}`}>
      {t("Your account is blocked for new bookings.")}
    </p>
  );
}

/** Amber banner explaining an account block; renders nothing when not blocked. */
export function BlockedNotice({ className = "" }: { className?: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (!user || !isAccountBlocked(user)) return null;
  const count = user.active_strikes ?? 0;
  return (
    <div
      role="status"
      className={`flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200 ${className}`}
    >
      <TriangleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {user.blocked_permanently
            ? t("Your account is blocked for new bookings indefinitely ({{count}} active strikes).", { count })
            : t("Your account is blocked for new bookings until {{date}} ({{count}} active strikes).", {
                count,
                date: formatDate(user.blocked_until),
              })}
        </p>
        <p className="mt-0.5">
          <Link to="/bookings#strikes" className="font-medium underline">
            {t("Show my strikes")}
          </Link>
          {" · "}
          {t("Questions? Please contact the lending team.")}
        </p>
      </div>
    </div>
  );
}
