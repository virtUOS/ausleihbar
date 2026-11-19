// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import i18n from "../../i18n";
import { ApiError } from "../../api";
import type { BatchResult } from "../types";

/** Field-keyed validation errors of a refused request (messages localized). */
export function fieldErrors(e: unknown): { fields: Record<string, string[]>; general: string | null } {
  const fields: Record<string, string[]> = {};
  if (e instanceof ApiError && e.data && typeof e.data === "object" && !Array.isArray(e.data)) {
    for (const [key, value] of Object.entries(e.data as Record<string, unknown>)) {
      const list = (Array.isArray(value) ? value : [value]).filter((m): m is string => typeof m === "string");
      if (key !== "detail" && key !== "non_field_errors" && list.length) fields[key] = list.map((m) => i18n.t(m));
    }
    const d = e.data as Record<string, unknown>;
    const other = [d.detail, d.non_field_errors]
      .flat()
      .filter((m): m is string => typeof m === "string")
      .map((m) => i18n.t(m));
    if (Object.keys(fields).length || other.length) return { fields, general: other.join(" ") || null };
  }
  return { fields, general: e instanceof Error ? e.message : i18n.t("The request failed.") };
}

/** The error text of one field (several fields may map to the same input). */
export function errorOf(fields: Record<string, string[]>, ...keys: string[]): string | null {
  const list = keys.flatMap((k) => fields[k] ?? []);
  return list.length ? list.join(" ") : null;
}

export function FieldError({ id, message }: { id: string; message: string | null }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="mt-1 text-xs font-medium text-red-700 dark:text-red-300">
      {message}
    </p>
  );
}

/** What a dry run would create and what already exists. */
export function BatchPreview({ result }: { result: BatchResult }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-700" aria-live="polite">
      {result.created.length === 0 ? (
        <p className="text-slate-800 dark:text-slate-200">{t("Nothing new to create.")}</p>
      ) : (
        <div>
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            {t("{{count}} will be created", { count: result.created.length })}
          </p>
          <p className="text-slate-800 dark:text-slate-200">{result.created.join(", ")}</p>
        </div>
      )}
      {result.skipped.length > 0 && (
        <div>
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            {t("{{count}} exist already", { count: result.skipped.length })}
          </p>
          <p className="text-slate-600 dark:text-slate-300">{result.skipped.join(", ")}</p>
        </div>
      )}
    </div>
  );
}
