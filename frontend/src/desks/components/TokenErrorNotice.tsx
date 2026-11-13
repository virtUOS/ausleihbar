// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { CircleAlert } from "lucide-react";
import { useAuth } from "../../auth";
import type { TokenError } from "../errors";

/** Error of a token page; with a lapsed session it offers the login (which
 *  returns to this very URL). */
export function TokenErrorNotice({ error, className = "" }: { error: TokenError; className?: string }) {
  const { t } = useTranslation();
  const { login } = useAuth();
  return (
    <div
      role="alert"
      className={`rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100 ${className}`}
    >
      <p className="flex items-start gap-2">
        <CircleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
        {error.message}
      </p>
      {error.login && (
        <button
          type="button"
          onClick={login}
          className="mt-3 min-h-[44px] rounded-full bg-brand-500 px-5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400"
        >
          {t("Sign in")}
        </button>
      )}
    </div>
  );
}
