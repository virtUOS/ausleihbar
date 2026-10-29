// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { poolAccent } from "../poolAccent";

/** A pool chip in the pool's accent colour (#16; unknown pools → neutral). */
export function PoolChip({ label, accent }: { label: string; accent?: string | null }) {
  const a = poolAccent(accent);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs text-slate-700 dark:text-slate-200 ${a.border} ${a.tint}`}
    >
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${a.dot}`} />
      {label}
    </span>
  );
}
