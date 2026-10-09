// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { SortToggle } from "./SortToggle";
import { limitValue } from "../durations";
import type { LendingType } from "../types";

type Mode = "inherit" | "own";

/**
 * One lending-duration limit (min or max) with an "Inherit | Own value"
 * segmented toggle (#109). Inherit stores null and shows `inheritedHint`
 * (where the value comes from); own shows a number input in the product's
 * lending unit. Used by the product form (inherit from pool) and the device
 * form (inherit from product).
 */
export function DurationLimitField({
  label,
  value,
  onChange,
  unit,
  inheritLabel,
  inheritedHint,
  suggestion = null,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  unit: LendingType;
  /** Label of the inherit option, e.g. "Inherit from pool". */
  inheritLabel: string;
  /** What applies while inheriting (value + source). */
  inheritedHint: string;
  /** Prefill when switching to an own value (e.g. the inherited value). */
  suggestion?: number | null;
}) {
  const { t } = useTranslation();
  const labelId = useId();
  const hintId = useId();
  const [mode, setMode] = useState<Mode>(limitValue(value) ? "own" : "inherit");
  // Last own value, restored when toggling inherit → own again.
  const lastOwn = useRef<number | null>(limitValue(value));
  const unitLabel = unit === "hours" ? t("Hours") : t("Days");

  function choose(next: Mode) {
    if (next === mode) return;
    setMode(next);
    if (next === "inherit") {
      lastOwn.current = limitValue(value) ?? lastOwn.current;
      onChange(null);
    } else {
      onChange(lastOwn.current ?? limitValue(suggestion) ?? 1);
    }
  }

  return (
    <div role="group" aria-labelledby={labelId} className="text-xs text-slate-600 dark:text-slate-300">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span id={labelId}>{label}</span>
        <SortToggle<Mode>
          value={mode}
          onChange={choose}
          label={label}
          options={[
            { value: "inherit", label: inheritLabel },
            { value: "own", label: t("Own value") },
          ]}
        />
      </div>
      {mode === "own" && (
        <div className="mt-1 flex items-center gap-2">
          <input
            type="number"
            min={1}
            step={1}
            required
            value={value ?? ""}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              onChange(Number.isFinite(n) && n > 0 ? n : null);
            }}
            aria-label={`${label} (${unitLabel})`}
            aria-describedby={hintId}
            className="block w-28 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <span>{unitLabel}</span>
        </div>
      )}
      <p id={hintId} className="mt-1 text-slate-500 dark:text-slate-400">
        {mode === "own"
          ? t("Without an own value: {{value}}", { value: inheritedHint })
          : inheritedHint}
      </p>
    </div>
  );
}
