// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Curated per-pool accent palette (#16). Keys are stored on ResourcePool
 *  .accent_color; values are theme-aware Tailwind classes. Unknown/blank → neutral. */
export interface PoolAccent {
  bar: string;    // a solid accent bar/border colour (bg-*)
  dot: string;    // a small swatch/dot (bg-*)
  text: string;   // accent text colour
  tint: string;   // subtle tinted surface (bg-*)
  border: string; // accent border colour (border-*), light + dark
}

const PALETTE: Record<string, PoolAccent> = {
  neutral: { bar: "bg-slate-400 dark:bg-slate-500", dot: "bg-slate-400", text: "text-slate-600 dark:text-slate-300", tint: "bg-slate-50 dark:bg-slate-800/50", border: "border-slate-200 dark:border-slate-700" },
  amber:   { bar: "bg-amber-400",  dot: "bg-amber-400",  text: "text-amber-700 dark:text-amber-300",   tint: "bg-amber-50 dark:bg-amber-950/30",   border: "border-amber-300 dark:border-amber-500/40" },
  sky:     { bar: "bg-sky-400",    dot: "bg-sky-400",    text: "text-sky-700 dark:text-sky-300",       tint: "bg-sky-50 dark:bg-sky-950/30",       border: "border-sky-300 dark:border-sky-500/40" },
  emerald: { bar: "bg-emerald-400",dot: "bg-emerald-400",text: "text-emerald-700 dark:text-emerald-300",tint: "bg-emerald-50 dark:bg-emerald-950/30",border: "border-emerald-300 dark:border-emerald-500/40" },
  violet:  { bar: "bg-violet-400", dot: "bg-violet-400", text: "text-violet-700 dark:text-violet-300", tint: "bg-violet-50 dark:bg-violet-950/30", border: "border-violet-300 dark:border-violet-500/40" },
  rose:    { bar: "bg-rose-400",   dot: "bg-rose-400",   text: "text-rose-700 dark:text-rose-300",     tint: "bg-rose-50 dark:bg-rose-950/30",     border: "border-rose-300 dark:border-rose-500/40" },
  teal:    { bar: "bg-teal-400",   dot: "bg-teal-400",   text: "text-teal-700 dark:text-teal-300",     tint: "bg-teal-50 dark:bg-teal-950/30",     border: "border-teal-300 dark:border-teal-500/40" },
  orange:  { bar: "bg-orange-400", dot: "bg-orange-400", text: "text-orange-700 dark:text-orange-300", tint: "bg-orange-50 dark:bg-orange-950/30", border: "border-orange-300 dark:border-orange-500/40" },
};

export const POOL_ACCENT_KEYS = Object.keys(PALETTE);

export function poolAccent(key?: string | null): PoolAccent {
  return PALETTE[key || "neutral"] ?? PALETTE.neutral;
}
