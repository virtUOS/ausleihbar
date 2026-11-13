// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Shared plan math of the floor-plan viewer (`FloorPlanView`) and the plan
// editor (`FloorPlanEditor`): zoom/pan view transform and symbol sizing.

import type { PlaceKind } from "../types";

/** Zoom/pan of a plan drawn into a `viewBox="0 0 W H"`: the content group is
 *  `translate(x y) scale(k)`. */
export interface View {
  k: number;
  x: number;
  y: number;
}

export const MAX_ZOOM = 10;

/** Keep the zoom in [1, max] and the content covering the viewport. */
export function clampView(v: View, W: number, H: number, maxZoom = MAX_ZOOM): View {
  const k = Math.min(Math.max(v.k, 1), maxZoom);
  return {
    k,
    x: Math.min(0, Math.max(W * (1 - k), v.x)),
    y: Math.min(0, Math.max(H * (1 - k), v.y)),
  };
}

/** Zoom by `factor` about the view point (fx, fy), clamped. */
export function zoomViewAbout(
  v: View,
  factor: number,
  fx: number,
  fy: number,
  W: number,
  H: number,
  maxZoom = MAX_ZOOM,
): View {
  const k = Math.min(Math.max(v.k * factor, 1), maxZoom);
  const f = k / v.k;
  return clampView({ k, x: fx - (fx - v.x) * f, y: fy - (fy - v.y) * f }, W, H, maxZoom);
}

/** Size unit of place symbols and labels in plan coordinates: about 0.45 m
 *  when the scale is known (within sane bounds of the plan's diagonal),
 *  else a fortieth of the diagonal. */
export function symbolUnit(diag: number, scalePxPerM?: number | null): number {
  if (scalePxPerM) return Math.min(Math.max(0.45 * scalePxPerM, diag / 90), diag / 18);
  return diag / 40;
}

/** Width and height of a place symbol in plan units (`u` = symbolUnit). */
export function symbolSize(kind: PlaceKind, u: number): { w: number; h: number } {
  return kind === "meeting_room" ? { w: u * 3, h: u * 2 } : { w: u * 2, h: u * 2 };
}
