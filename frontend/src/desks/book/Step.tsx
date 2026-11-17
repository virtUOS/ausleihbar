// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";

/** A numbered step of the Book page. */
export function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`step-${n}`} className="mb-6">
      <h2
        id={`step-${n}`}
        className="mb-2 flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100"
      >
        <span
          aria-hidden
          className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-slate-900"
        >
          {n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}
