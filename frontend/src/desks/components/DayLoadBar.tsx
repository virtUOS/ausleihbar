// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import type { DayLoad, HalfLoad } from "../dayLoad";

// Shape, not colour alone: empty = free, half filled = partly, full = booked.
const fillHeight = (load: HalfLoad) => (load === "full" ? 1 : load === "part" ? 0.5 : 0);

function Segment({ load }: { load: HalfLoad | null }) {
  if (load === null) {
    return <span className="h-3 w-5 rounded-sm border border-dashed border-slate-300 dark:border-slate-600" />;
  }
  return (
    <span className="relative h-3 w-5 overflow-hidden rounded-sm border border-red-700 bg-white dark:border-red-400 dark:bg-slate-900">
      <span
        className="absolute inset-x-0 bottom-0 bg-red-600 dark:bg-red-400"
        style={{ height: `${fillHeight(load) * 100}%` }}
      />
    </span>
  );
}

/** Morning | afternoon load of a place's day (decorative; the text goes into
 *  the place's accessible name). */
export function DayLoadBar({ load }: { load: DayLoad }) {
  return (
    <span aria-hidden className="inline-flex shrink-0 items-center gap-0.5">
      <Segment load={load.morning} />
      <Segment load={load.afternoon} />
    </span>
  );
}

/** Legend entry explaining the bar. */
export function DayLoadLegend({ t }: { t: TFunction }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 dark:text-slate-200">
      <DayLoadBar load={{ morning: "full", afternoon: "part" }} />
      {t("Morning | afternoon (full: booked, half: partly)")}
    </span>
  );
}

/** The same bar in plan units (`u`), centred above a plan symbol. */
export function DayLoadSvg({ load, u, y }: { load: DayLoad; u: number; y: number }) {
  const w = u * 0.9;
  const h = u * 0.5;
  const gap = u * 0.12;
  const seg = (l: HalfLoad | null, x: number) => (
    <g key={x} transform={`translate(${x} ${y})`}>
      <rect
        width={w}
        height={h}
        rx={u * 0.1}
        vectorEffect="non-scaling-stroke"
        strokeWidth={1}
        strokeDasharray={l === null ? "2 2" : undefined}
        className={
          l === null
            ? "fill-none stroke-slate-300 dark:stroke-slate-600"
            : "fill-white stroke-red-700 dark:fill-slate-900 dark:stroke-red-400"
        }
      />
      {l !== null && fillHeight(l) > 0 && (
        <rect
          y={h * (1 - fillHeight(l))}
          width={w}
          height={h * fillHeight(l)}
          className="fill-red-600 dark:fill-red-400"
        />
      )}
    </g>
  );
  return (
    <g aria-hidden>
      {seg(load.morning, -w - gap / 2)}
      {seg(load.afternoon, gap / 2)}
    </g>
  );
}
