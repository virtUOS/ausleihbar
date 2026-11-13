// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import type { HourState } from "../types";

/** State of a place as drawn: the overview hour states. */
export type DrawState = HourState;

interface StateMeta {
  /** Glyph drawn in the symbol so the state never relies on colour alone. */
  glyph: string;
  /** SVG classes of the symbol body (fill + stroke, light and dark). */
  body: string;
  /** SVG class of the glyph. */
  ink: string;
  /** HTML classes of a pill / legend swatch. */
  pill: string;
  dash?: string;
}

export const STATE_META: Record<DrawState, StateMeta> = {
  free: {
    glyph: "✓",
    body: "fill-green-100 stroke-green-700 dark:fill-green-950 dark:stroke-green-400",
    ink: "fill-green-800 dark:fill-green-300",
    pill: "border-green-700 bg-green-100 text-green-900 dark:border-green-400 dark:bg-green-950/60 dark:text-green-200",
  },
  booked: {
    glyph: "✕",
    body: "fill-red-100 stroke-red-700 dark:fill-red-950 dark:stroke-red-400",
    ink: "fill-red-800 dark:fill-red-300",
    pill: "border-red-700 bg-red-100 text-red-900 dark:border-red-400 dark:bg-red-950/60 dark:text-red-200",
  },
  late: {
    glyph: "!",
    body: "fill-red-100 stroke-red-700 dark:fill-red-950 dark:stroke-red-400",
    ink: "fill-red-800 dark:fill-red-300",
    pill: "border-red-700 bg-red-100 text-red-900 dark:border-red-400 dark:bg-red-950/60 dark:text-red-200",
    dash: "4 2",
  },
  potentially_free: {
    glyph: "?",
    body: "fill-amber-100 stroke-amber-700 dark:fill-amber-950 dark:stroke-amber-400",
    ink: "fill-amber-800 dark:fill-amber-300",
    pill: "border-dashed border-amber-700 bg-amber-100 text-amber-900 dark:border-amber-400 dark:bg-amber-950/60 dark:text-amber-200",
    dash: "4 2",
  },
  checked_in: {
    glyph: "●",
    body: "fill-sky-100 stroke-sky-700 dark:fill-sky-950 dark:stroke-sky-400",
    ink: "fill-sky-800 dark:fill-sky-300",
    pill: "border-sky-700 bg-sky-100 text-sky-900 dark:border-sky-400 dark:bg-sky-950/60 dark:text-sky-200",
  },
  closed: {
    glyph: "–",
    body: "fill-slate-100 stroke-slate-400 dark:fill-slate-800 dark:stroke-slate-500",
    ink: "fill-slate-600 dark:fill-slate-300",
    pill: "border-slate-400 bg-slate-100 text-slate-700 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-300",
  },
};

export const stateMeta = (s: string): StateMeta => STATE_META[s as DrawState] ?? STATE_META.closed;

export function stateLabel(t: TFunction, s: string): string {
  switch (s) {
    case "free":
      return t("Free");
    case "booked":
      return t("Booked");
    case "late":
      return t("Booked, not yet here");
    case "potentially_free":
      return t("Possibly free");
    case "checked_in":
      return t("Checked in");
    default:
      return t("Closed");
  }
}

const LEGEND: DrawState[] = ["free", "booked", "potentially_free", "checked_in"];

/** Legend: colour + glyph + text, so no state depends on colour alone. */
export function StateLegend({ t }: { t: TFunction }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700 dark:text-slate-200">
      {LEGEND.map((s) => (
        <li key={s} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className={`inline-flex h-5 w-5 items-center justify-center rounded-md border text-[11px] font-bold ${stateMeta(s).pill}`}
          >
            {stateMeta(s).glyph}
          </span>
          {stateLabel(t, s)}
        </li>
      ))}
    </ul>
  );
}
