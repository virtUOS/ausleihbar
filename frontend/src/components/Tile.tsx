// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import type { Crumb } from "./Breadcrumbs";
import { poolAccent } from "../poolAccent";

/** Image-led tile: the picture IS the tile, text sits below it. The image well
 *  matches the admin crop ratio so uploads show exactly as cropped. Shared by
 *  the start page (sections, pools) and category pages (subcategories). */
export function Tile({
  to,
  imageUrl,
  imageAspect,
  fallback,
  fallbackBg,
  title,
  subtitle,
  accentColor,
  crumbs,
}: {
  to: string;
  imageUrl: string | null;
  imageAspect: string;
  fallback: string;
  fallbackBg: string;
  title: string;
  subtitle?: string;
  /** Pool accent palette key (#16); renders a small dot beside the title. */
  accentColor?: string;
  /** Breadcrumb trail to carry to the target page (router state). */
  crumbs?: Crumb[];
}) {
  // Pool tiles carry an accent colour (#16): its tint replaces the fixed
  // brand fallback background, and a thin bar anchors the tile to its pool.
  const accent = accentColor ? poolAccent(accentColor) : null;
  return (
    <Link
      to={to}
      state={crumbs ? { crumbs } : undefined}
      className="group overflow-hidden rounded-2xl border border-slate-200 bg-white transition-all duration-200 ease-out-quart hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md hover:shadow-slate-900/[0.04] dark:border-slate-800 dark:bg-slate-900"
    >
      <div
        className={`flex ${imageAspect} w-full items-center justify-center overflow-hidden ${
          imageUrl ? "bg-slate-100 dark:bg-slate-800" : accent ? accent.tint : fallbackBg
        }`}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt=""
            className="h-full w-full object-cover transition-transform duration-300 ease-out-quart group-hover:scale-[1.04]"
          />
        ) : (
          <span
            aria-hidden
            className="text-4xl transition-transform duration-300 ease-out-quart group-hover:scale-110"
          >
            {fallback}
          </span>
        )}
      </div>
      {accent && <div aria-hidden className={`h-1 w-full ${accent.bar}`} />}
      <div className="px-3.5 py-3">
        <p className="flex items-center gap-1.5 font-bold leading-snug text-slate-900 dark:text-slate-100">
          {accent && (
            <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${accent.dot}`} />
          )}
          <span className="truncate">{title}</span>
        </p>
        {subtitle && <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">{subtitle}</p>}
      </div>
    </Link>
  );
}
