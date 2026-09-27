// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/**
 * `RichText`'s `className` prop REPLACES its default prose styling — it does
 * not merge with it. Any spot that passes a compact/muted `className` to fit
 * a tight layout (pool description/directions, the landing page's pool
 * tiles) must re-supply list/link/heading styling itself, or it silently
 * loses bullets, numbered lists and heading emphasis — and links become
 * indistinguishable from plain text (WCAG 1.4.1). Combine this with the
 * spot's own size/colour classes, e.g. `` `${RICH_TEXT_COMPACT} text-sm …` ``.
 *
 * Kept as one static string (no interpolation) so Tailwind's JIT scanner can
 * see every class here regardless of how call sites combine it.
 */
export const RICH_TEXT_COMPACT =
  "[&_p]:my-1 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-0.5 [&_a]:font-medium [&_a]:underline [&_a]:text-brand-700 dark:[&_a]:text-brand-300 [&_h2]:mt-2 [&_h2]:font-semibold [&_h2]:text-slate-900 dark:[&_h2]:text-slate-100 [&_h3]:mt-2 [&_h3]:font-semibold [&_strong]:font-semibold [&_em]:italic [&_img]:max-w-full [&_img]:h-auto";
