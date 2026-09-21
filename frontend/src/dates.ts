// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Shared, locale-aware date formatting for display (issue #22): dates follow
 *  the active UI language (e.g. 21.09.2026 in German, 09/21/2026 in English)
 *  instead of a hardcoded locale. Internal ISO values (date inputs, keys) keep
 *  using the fixed "en-CA" formatting elsewhere and must not use these. */

import i18n from "./i18n";

/** A date without time, in the active UI language. Returns "–" for empty. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString(i18n.language, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** A date with time, in the active UI language. Returns "–" for empty. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString(i18n.language, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
