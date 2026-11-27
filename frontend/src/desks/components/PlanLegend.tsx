// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Info } from "lucide-react";
import { useOutsideClose } from "../../useOutsideClose";
import { DayLoadBar } from "./DayLoadBar";
import { stateLabel, stateMeta } from "./placeStates";

const STATES = ["free", "booked", "potentially_free"] as const;

const legendLabel = (t: TFunction, state: (typeof STATES)[number]) =>
  state === "potentially_free" ? t("Maybe free") : stateLabel(t, state);

/** One-line legend of the plan: the three states, the day ring (morning |
 *  afternoon) and an ⓘ button explaining the ring (click, hover or focus;
 *  Escape closes). Wraps below 640 px. */
export function PlanLegend() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const rootRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const popId = useId();
  const shown = open || hover || focus;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700 dark:text-slate-200">
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {STATES.map((state) => (
          <li key={state} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className={`inline-flex h-5 w-5 items-center justify-center rounded-md border text-[11px] font-bold ${stateMeta(state).pill}`}
            >
              {stateMeta(state).glyph}
            </span>
            {legendLabel(t, state)}
          </li>
        ))}
      </ul>
      <div
        ref={rootRef}
        className="relative inline-flex items-center gap-1"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && shown) {
            setOpen(false);
            setHover(false);
            setFocus(false);
          }
        }}
      >
        <DayLoadBar load={{ morning: "full", afternoon: "part" }} />
        <span>{t("Morning | afternoon")}</span>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={popId}
          aria-label={t("About the ring")}
          onClick={() => {
            if (open) setFocus(false);
            setOpen(!open);
          }}
          onFocus={(e) => setFocus(e.currentTarget.matches(":focus-visible"))}
          onBlur={() => setFocus(false)}
          className="group flex min-h-[44px] min-w-[44px] items-center justify-center"
        >
          <Info aria-hidden className="h-4 w-4 text-slate-500 group-hover:text-slate-800 dark:text-slate-400 dark:group-hover:text-slate-100" />
        </button>
        {shown && (
          <div
            id={popId}
            role="note"
            className="absolute left-0 top-full z-30 w-72 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-800 shadow-lg dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            {t("Ring: left morning, right afternoon (solid: fewer than 4 hours in a row left, dashed: partly booked)")}
          </div>
        )}
      </div>
    </div>
  );
}
