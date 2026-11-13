// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Document model and undo history of the floor-plan editor. The document is
// what "Speichern" writes: the plan shapes (`Floor.plan`), the place symbols
// (`Place.plan_symbol`) and the scale (`Floor.scale_px_per_m`), all in plan
// coordinates — so an automatically redrawn plan can later be imported as the
// same data.

import type { PlanShape, PlanSymbol } from "../types";

export type Point = [number, number];

export interface PlanDoc {
  shapes: PlanShape[];
  /** Symbol per place id (null = not on the plan). */
  symbols: Record<number, PlanSymbol | null>;
  /** Plan units per metre; null = not set. */
  scale: number | null;
}

export interface History {
  past: PlanDoc[];
  present: PlanDoc;
  future: PlanDoc[];
}

/** Undo depth (the plan asks for at least 20 steps). */
export const HISTORY_LIMIT = 50;

export type HistoryAction =
  /** A finished change: one undo step. */
  | { type: "commit"; doc: PlanDoc }
  /** An intermediate state of a running gesture (drag, typing): no step. */
  | { type: "live"; doc: PlanDoc }
  /** End of a gesture that started at `before`: one step if anything changed. */
  | { type: "endGesture"; before: PlanDoc }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "reset"; doc: PlanDoc };

const pushPast = (past: PlanDoc[], doc: PlanDoc) => [...past, doc].slice(-HISTORY_LIMIT);

export function historyReducer(h: History, a: HistoryAction): History {
  switch (a.type) {
    case "commit":
      if (a.doc === h.present) return h;
      return { past: pushPast(h.past, h.present), present: a.doc, future: [] };
    case "live":
      return { ...h, present: a.doc };
    case "endGesture":
      if (a.before === h.present) return h;
      // A gesture that ended where it started (jitter, drag and back) is no
      // step and restores the original objects, so nothing reads as changed.
      if (sameDoc(a.before, h.present)) return { ...h, present: a.before };
      return { past: pushPast(h.past, a.before), present: h.present, future: [] };
    case "undo":
      if (!h.past.length) return h;
      return {
        past: h.past.slice(0, -1),
        present: h.past[h.past.length - 1],
        future: [h.present, ...h.future],
      };
    case "redo":
      if (!h.future.length) return h;
      return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) };
    case "reset":
      return { past: [], present: a.doc, future: [] };
  }
}

/** Plan coordinates are stored with one decimal. */
export const round1 = (n: number) => Math.round(n * 10) / 10;

/** Grid of the snap: 10 cm with a scale, else 10 plan units. */
export const gridSize = (scale: number | null) => (scale ? scale * 0.1 : 10);

export function snap(p: Point, grid: number | null): Point {
  if (!grid) return [round1(p[0]), round1(p[1])];
  return [round1(Math.round(p[0] / grid) * grid), round1(Math.round(p[1] / grid) * grid)];
}

export function newShapeId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }
}

export function translateShape(s: PlanShape, dx: number, dy: number): PlanShape {
  return {
    ...s,
    points: (s.points ?? []).map(([x, y]) => [round1(x + dx), round1(y + dy)] as Point),
  };
}

/** Drops consecutive duplicate points (a double-click adds its point twice). */
export function dedupePoints(points: Point[]): Point[] {
  return points.filter(
    (p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1],
  );
}

export const sameSymbol = (a: PlanSymbol | null | undefined, b: PlanSymbol | null | undefined) =>
  (a ?? null) === (b ?? null) ||
  (!!a && !!b && a.x === b.x && a.y === b.y && (a.rotation || 0) === (b.rotation || 0));

/** Ids of the places whose symbol differs between two documents. */
export function changedSymbolIds(a: PlanDoc, b: PlanDoc): number[] {
  const ids = new Set([...Object.keys(a.symbols), ...Object.keys(b.symbols)].map(Number));
  return [...ids].filter((id) => !sameSymbol(a.symbols[id], b.symbols[id]));
}

export const sameShapes = (a: PlanShape[], b: PlanShape[]) =>
  a === b || JSON.stringify(a) === JSON.stringify(b);

/** Value equality of two documents. */
export function sameDoc(a: PlanDoc, b: PlanDoc): boolean {
  return (
    (a.scale ?? null) === (b.scale ?? null) &&
    sameShapes(a.shapes, b.shapes) &&
    changedSymbolIds(a, b).length === 0
  );
}

/** Keeps a point on the canvas [0, W] × [0, H]. */
export const clampPoint = (p: Point, W: number, H: number): Point => [
  Math.min(Math.max(p[0], 0), W),
  Math.min(Math.max(p[1], 0), H),
];

/** Limits a translation (dx, dy) so every point stays on the canvas. */
export function clampDelta(points: Point[], dx: number, dy: number, W: number, H: number): Point {
  if (!points.length) return [dx, dy];
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [
    Math.min(Math.max(dx, -Math.min(...xs)), W - Math.max(...xs)),
    Math.min(Math.max(dy, -Math.min(...ys)), H - Math.max(...ys)),
  ];
}

/** Centroid of a polygon's vertices (good enough for a room label). */
export function centroid(points: Point[]): Point {
  const n = points.length || 1;
  return [
    points.reduce((s, p) => s + p[0], 0) / n,
    points.reduce((s, p) => s + p[1], 0) / n,
  ];
}

/** Length in metres, parsed from user input ("3,5" or "3.5"); null if invalid. */
export function parseMetres(raw: string): number | null {
  const v = Number(raw.trim().replace(",", "."));
  return Number.isFinite(v) && v > 0 ? v : null;
}
