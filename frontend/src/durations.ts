// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Lending-duration labels (#109). Limits are counted in the product's lending
// unit (days or hours); null (or 0) means "no limit" / "inherit".

import i18n from "./i18n";
import type { LendingType, PoolDurationLimit } from "./types";

/** A set limit, or null for "not set" (0 counts as not set, like the backend). */
export const limitValue = (v: number | null | undefined): number | null =>
  v && v > 0 ? v : null;

/** "3 days" / "1 hour" in the given lending unit. */
export function durationCount(value: number, unit: LendingType): string {
  return unit === "hours"
    ? i18n.t("{{count}} hour", { count: value })
    : i18n.t("{{count}} day", { count: value });
}

/** Human range: "1–7 days", "at least 2 days", "at most 7 days", "3 hours"
 *  (min = max) or "not limited". */
export function durationRange(
  min: number | null | undefined,
  max: number | null | undefined,
  unit: LendingType,
): string {
  const lo = limitValue(min);
  const hi = limitValue(max);
  if (lo && hi) {
    return lo === hi ? durationCount(hi, unit) : `${lo}–${durationCount(hi, unit)}`;
  }
  if (lo) return i18n.t("at least {{value}}", { value: durationCount(lo, unit) });
  if (hi) return i18n.t("at most {{value}}", { value: durationCount(hi, unit) });
  return i18n.t("Not limited");
}

/** Whether the pools' ranges differ (then each pool's range is listed). */
export function poolLimitsDiffer(rows: PoolDurationLimit[]): boolean {
  return rows.some(
    (r) =>
      limitValue(r.min) !== limitValue(rows[0].min) ||
      limitValue(r.max) !== limitValue(rows[0].max),
  );
}

/** "DigiLab: at most 7 days · Videostudio: not limited". */
export function poolLimitsLabel(rows: PoolDurationLimit[], unit: LendingType): string {
  return rows.map((r) => `${r.pool_name}: ${durationRange(r.min, r.max, unit)}`).join(" · ");
}
