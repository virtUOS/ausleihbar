// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import type { DayLoad, HalfLoad } from "../dayLoad";

// A ring around the place: left half = morning, right half = afternoon.
// Line style, not colour alone: solid = booked, dashed = partly, thin = free.
// Degrees left open between the halves: a small gap at the top, a wider one
// at the bottom where the plan draws the place name.
const TOP_GAP = 12;
const BOTTOM_GAP = 40;

/** Point on a circle, angle in degrees clockwise from the top. */
const pt = (r: number, a: number) => {
  const rad = (a * Math.PI) / 180;
  return `${(r * Math.sin(rad)).toFixed(3)} ${(-r * Math.cos(rad)).toFixed(3)}`;
};
const arc = (r: number, a0: number, a1: number) => `M ${pt(r, a0)} A ${r} ${r} 0 0 1 ${pt(r, a1)}`;

function Half({ load, r, d, width }: { load: HalfLoad | null; r: number; d: [number, number]; width: number }) {
  if (load === null) return null;
  const path = arc(r, d[0], d[1]);
  if (load === "free") {
    return (
      <path d={path} fill="none" strokeWidth={1} vectorEffect="non-scaling-stroke" className="stroke-slate-300 dark:stroke-slate-600" />
    );
  }
  return (
    <path
      d={path}
      fill="none"
      strokeWidth={width}
      strokeLinecap="round"
      strokeDasharray={load === "part" ? `${width * 1.2} ${width * 1.2}` : undefined}
      vectorEffect="non-scaling-stroke"
      className="stroke-brand-600 dark:stroke-brand-400"
    />
  );
}

/** The two half rings of radius `r` around (0, 0); `width` in screen px. */
function Ring({ load, r, width }: { load: DayLoad; r: number; width: number }) {
  return (
    <g aria-hidden>
      <Half load={load.morning} r={r} d={[180 + BOTTOM_GAP, 360 - TOP_GAP]} width={width} />
      <Half load={load.afternoon} r={r} d={[TOP_GAP, 180 - BOTTOM_GAP]} width={width} />
    </g>
  );
}

/** Small ring icon for lists and the legend (decorative; the text goes into
 *  the place's accessible name). */
export function DayLoadBar({ load }: { load: DayLoad }) {
  return (
    <svg aria-hidden viewBox="-11 -11 22 22" className="h-7 w-7 shrink-0">
      <circle r={3} className="fill-slate-300 dark:fill-slate-600" />
      <Ring load={load} r={8} width={2.5} />
    </svg>
  );
}

/** Legend entry explaining the ring. */
export function DayLoadLegend({ t }: { t: TFunction }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 dark:text-slate-200">
      <DayLoadBar load={{ morning: "full", afternoon: "part" }} />
      {t("Ring: left morning, right afternoon (solid booked, dashed partly)")}
    </span>
  );
}

/** The ring around a plan symbol of radius `r` (plan units). */
export function DayLoadSvg({ load, r }: { load: DayLoad; r: number }) {
  return <Ring load={load} r={r} width={3} />;
}
