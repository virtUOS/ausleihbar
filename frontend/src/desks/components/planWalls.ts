// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Pure geometry of room walls and the doors/windows bound to them (plan
// units). A wall-bound opening stores its room shape, the edge index and the
// relative position `t` of its centre along that edge, so it follows the
// room's corners; these helpers resolve it to points, cut the wall gaps and
// keep the binding intact when corners are inserted or removed.

import type { PlanShape, WallRef } from "../types";
import { round1, type Point } from "./planEditorState";

/** Distance (plan units) within which a point counts as lying on a wall. */
const ON_WALL = 0.5;
/** Distance within which two room corners count as the same corner. */
const SAME_CORNER = 0.05;

const ptsOf = (s: PlanShape) => (s.points ?? []).filter((p) => p.length >= 2) as Point[];
const isRoom = (s: PlanShape) => s.type === "room";
const isOpening = (s: PlanShape) => (s.type === "door" || s.type === "window") && !!s.wall;
const dist = (a: Point, b: Point) => Math.hypot(b[0] - a[0], b[1] - a[1]);
const lerp = (a: Point, b: Point, t: number): Point => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/** Projection of `p` onto the segment a→b: parameter (0–1), point, distance. */
function project(a: Point, b: Point, p: Point): { t: number; point: Point; dist: number } {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2, 0, 1) : 0;
  const point = lerp(a, b, t);
  return { t, point, dist: dist(point, p) };
}

/** Edge `edge` of a room shape: point i → point (i+1) mod n. */
export function edgeOf(room: PlanShape, edge: number): [Point, Point] | null {
  const pts = ptsOf(room);
  const n = pts.length;
  if (!isRoom(room) || n < 2 || !Number.isInteger(edge) || edge < 0 || edge >= n) return null;
  return [pts[edge], pts[(edge + 1) % n]];
}

/** The two end points of a wall-bound door/window on its wall (`a` towards
 *  the edge's start), its width clamped to the edge length and its centre
 *  kept so the opening fits the edge. Null for old two-point doors and
 *  broken references. */
export function openingSegment(
  shapes: PlanShape[],
  s: PlanShape,
): { a: Point; b: Point; room: PlanShape } | null {
  if (!isOpening(s) || !s.width || !(s.width > 0)) return null;
  const room = shapes.find((r) => r.id === s.wall!.shape && isRoom(r));
  const e = room && edgeOf(room, s.wall!.edge);
  if (!room || !e) return null;
  const len = dist(e[0], e[1]);
  if (!len) return null;
  const half = Math.min(s.width, len) / 2 / len;
  const t = clamp(s.wall!.t, half, 1 - half);
  return { a: lerp(e[0], e[1], t - half), b: lerp(e[0], e[1], t + half), room };
}

/** The room edge nearest to `p` within `maxDist`, with the position on it. */
export function nearestRoomEdge(
  shapes: PlanShape[],
  p: Point,
  maxDist: number,
): { shape: string; edge: number; t: number; point: Point; dist: number } | null {
  let best: { shape: string; edge: number; t: number; point: Point; dist: number } | null = null;
  for (const s of shapes) {
    if (!isRoom(s)) continue;
    const n = ptsOf(s).length;
    for (let i = 0; i < n; i++) {
      const e = edgeOf(s, i);
      if (!e) continue;
      const pr = project(e[0], e[1], p);
      if (pr.dist <= maxDist && (!best || pr.dist < best.dist))
        best = { shape: s.id, edge: i, t: pr.t, point: pr.point, dist: pr.dist };
    }
  }
  return best;
}

/** Docking target for `p`: the nearest room corner within `maxDist`, else
 *  the nearest point on a room edge, else null. Shape `exclude` is ignored. */
export function snapToRooms(
  shapes: PlanShape[],
  p: Point,
  maxDist: number,
  exclude?: string,
): Point | null {
  const others = exclude ? shapes.filter((s) => s.id !== exclude) : shapes;
  let corner: Point | null = null;
  let cd = Infinity;
  for (const s of others) {
    if (!isRoom(s)) continue;
    for (const c of ptsOf(s)) {
      const d = dist(c, p);
      if (d <= maxDist && d < cd) (corner = c), (cd = d);
    }
  }
  if (corner) return [corner[0], corner[1]];
  const edge = nearestRoomEdge(others, p, maxDist);
  return edge ? [round1(edge.point[0]), round1(edge.point[1])] : null;
}

/** Every room corner lying on `p` (docked rooms share it), except `exclude`. */
export function coincidentCorners(
  shapes: PlanShape[],
  p: Point,
  exclude?: { shape: string; index: number },
): { shape: string; index: number }[] {
  const out: { shape: string; index: number }[] = [];
  for (const s of shapes) {
    if (!isRoom(s)) continue;
    ptsOf(s).forEach((c, index) => {
      if (exclude && exclude.shape === s.id && exclude.index === index) return;
      if (dist(c, p) <= SAME_CORNER) out.push({ shape: s.id, index });
    });
  }
  return out;
}

/** The absolute centre of an opening on its (old) edge, unclamped. */
const centreOn = (e: [Point, Point], w: WallRef) => lerp(e[0], e[1], w.t);

/** Re-binds every opening on `roomId`: `map(edge)` gives either a new edge
 *  index (t unchanged) or null, when the opening's centre has to be placed
 *  on the best of `candidates` of the new room. */
function rebind(
  shapes: PlanShape[],
  roomId: string,
  oldRoom: PlanShape,
  newRoom: PlanShape,
  map: (edge: number) => number | null,
  candidates: number[],
): PlanShape[] {
  return shapes.map((s) => {
    if (s.id === roomId) return newRoom;
    if (!isOpening(s) || s.wall!.shape !== roomId) return s;
    const w = s.wall!;
    const idx = map(w.edge);
    if (idx !== null) return idx === w.edge ? s : { ...s, wall: { ...w, edge: idx } };
    const old = edgeOf(oldRoom, w.edge);
    if (!old) return s;
    const c = centreOn(old, w);
    let best: { edge: number; t: number; dist: number } | null = null;
    for (const i of candidates) {
      const e = edgeOf(newRoom, i);
      if (!e) continue;
      const pr = project(e[0], e[1], c);
      if (!best || pr.dist < best.dist) best = { edge: i, t: pr.t, dist: pr.dist };
    }
    return best ? { ...s, wall: { ...w, edge: best.edge, t: best.t } } : s;
  });
}

/** Inserts corner `p` into edge `edge` of room `roomId` (after point `edge`).
 *  Openings keep their absolute position (edge indices and `t` re-mapped). */
export function insertCorner(shapes: PlanShape[], roomId: string, edge: number, p: Point): PlanShape[] {
  const room = shapes.find((s) => s.id === roomId && isRoom(s));
  if (!room || !edgeOf(room, edge)) return shapes;
  const pts = ptsOf(room);
  const q: Point = [round1(p[0]), round1(p[1])];
  const newRoom: PlanShape = { ...room, points: [...pts.slice(0, edge + 1), q, ...pts.slice(edge + 1)] };
  return rebind(
    shapes,
    roomId,
    room,
    newRoom,
    (e) => (e === edge ? null : e > edge ? e + 1 : e),
    [edge, edge + 1],
  );
}

/** Removes corner `index` of room `roomId` (only while ≥ 3 corners remain).
 *  Openings on the two edges at that corner move to the merged edge at the
 *  same absolute position; the others keep theirs. */
export function removeCorner(shapes: PlanShape[], roomId: string, index: number): PlanShape[] {
  const room = shapes.find((s) => s.id === roomId && isRoom(s));
  if (!room) return shapes;
  const pts = ptsOf(room);
  const n = pts.length;
  if (n <= 3 || !Number.isInteger(index) || index < 0 || index >= n) return shapes;
  const newRoom: PlanShape = { ...room, points: pts.filter((_, i) => i !== index) };
  const before = (index - 1 + n) % n;
  const merged = index === 0 ? n - 2 : index - 1;
  return rebind(
    shapes,
    roomId,
    room,
    newRoom,
    (e) => (e === before || e === index ? null : e < index ? e : e - 1),
    [merged],
  );
}

/** Removes a room shape together with the doors/windows bound to it. */
export function removeRoom(shapes: PlanShape[], roomId: string): PlanShape[] {
  return shapes.filter((s) => s.id !== roomId && !(isOpening(s) && s.wall!.shape === roomId));
}

/** The 4 corners of the axis-aligned rectangle spanned by a and b, clockwise
 *  on screen (y down) from the top left. */
export function rectPoints(a: Point, b: Point): Point[] {
  const x0 = Math.min(a[0], b[0]);
  const x1 = Math.max(a[0], b[0]);
  const y0 = Math.min(a[1], b[1]);
  const y1 = Math.max(a[1], b[1]);
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

/** Unit normal of edge p→q pointing into the room (by the polygon's winding). */
export function inwardNormal(room: PlanShape, edge: number): Point | null {
  const e = edgeOf(room, edge);
  if (!e) return null;
  const len = dist(e[0], e[1]);
  if (!len) return null;
  const pts = ptsOf(room);
  let area2 = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % pts.length];
    area2 += x1 * y2 - x2 * y1;
  }
  const ex = (e[1][0] - e[0][0]) / len;
  const ey = (e[1][1] - e[0][1]) / len;
  return area2 >= 0 ? [-ey, ex] : [ey, -ex];
}

/** The wall pieces of a room's outline: its edges minus every wall-bound
 *  opening lying on them — also openings bound to another room whose edge
 *  runs along this one (a door on a shared wall breaks both outlines). */
export function wallSegments(shapes: PlanShape[], room: PlanShape): [Point, Point][] {
  const openings = shapes
    .map((s) => openingSegment(shapes, s))
    .filter((o): o is NonNullable<typeof o> => !!o);
  const out: [Point, Point][] = [];
  const n = ptsOf(room).length;
  for (let i = 0; i < n; i++) {
    const e = edgeOf(room, i);
    if (!e) continue;
    const [p, q] = e;
    const len = dist(p, q);
    if (!len) continue;
    const ux = (q[0] - p[0]) / len;
    const uy = (q[1] - p[1]) / len;
    // Signed distance from the edge line and position along it.
    const off = (r: Point) => (r[0] - p[0]) * -uy + (r[1] - p[1]) * ux;
    const pos = (r: Point) => (r[0] - p[0]) * ux + (r[1] - p[1]) * uy;
    const cuts: [number, number][] = [];
    for (const o of openings) {
      if (Math.abs(off(o.a)) > ON_WALL || Math.abs(off(o.b)) > ON_WALL) continue;
      const lo = Math.max(0, Math.min(pos(o.a), pos(o.b)));
      const hi = Math.min(len, Math.max(pos(o.a), pos(o.b)));
      if (hi - lo > 1e-6) cuts.push([lo, hi]);
    }
    cuts.sort((x, y) => x[0] - y[0]);
    let from = 0;
    for (const [lo, hi] of cuts) {
      if (lo > from + 1e-6) out.push([lerp(p, q, from / len), lerp(p, q, lo / len)]);
      from = Math.max(from, hi);
    }
    if (from < len - 1e-6) out.push([lerp(p, q, from / len), q]);
  }
  return out;
}

/** Drawing of a wall-bound door: hinge, leaf end (perpendicular to the wall,
 *  length = width, into the room unless `flip_swing`), the free end of the
 *  opening and the sweep flag of the quarter arc leaf end → free end. */
export function doorGeometry(
  shapes: PlanShape[],
  s: PlanShape,
): { hinge: Point; leaf: Point; free: Point; r: number; sweep: 0 | 1 } | null {
  const seg = openingSegment(shapes, s);
  if (!seg || s.type !== "door") return null;
  const n = inwardNormal(seg.room, s.wall!.edge);
  if (!n) return null;
  const [hinge, free] = s.flip_hinge ? [seg.b, seg.a] : [seg.a, seg.b];
  const r = dist(hinge, free);
  const k = s.flip_swing ? -r : r;
  const leaf: Point = [hinge[0] + n[0] * k, hinge[1] + n[1] * k];
  const v1 = [leaf[0] - hinge[0], leaf[1] - hinge[1]];
  const v2 = [free[0] - hinge[0], free[1] - hinge[1]];
  return { hinge, leaf, free, r, sweep: v1[0] * v2[1] - v1[1] * v2[0] > 0 ? 1 : 0 };
}

// --- Editing helpers (plan editor) ------------------------------------------

/** Docking target of a drawn point: a room corner within `maxDist`, else a
 *  point on a room edge, else each axis aligned to a room corner's x / y
 *  within `maxDist`, else the grid (or one decimal without a grid). Pass the
 *  shapes the point may dock to (without the ones being edited). */
export function dockPoint(shapes: PlanShape[], p: Point, maxDist: number, grid: number | null): Point {
  const hit = snapToRooms(shapes, p, maxDist);
  if (hit) return hit;
  const onGrid = (v: number) => round1(grid ? Math.round(v / grid) * grid : v);
  const align = (axis: 0 | 1) => {
    let best: number | null = null;
    let bd = maxDist;
    for (const s of shapes) {
      if (!isRoom(s)) continue;
      for (const c of ptsOf(s)) {
        const d = Math.abs(c[axis] - p[axis]);
        if (d <= bd) (best = c[axis]), (bd = d);
      }
    }
    return best ?? onGrid(p[axis]);
  };
  return [align(0), align(1)];
}

/** Moves the given corners to `p` (docked rooms share a corner). */
export function moveCorners(shapes: PlanShape[], corners: { shape: string; index: number }[], p: Point): PlanShape[] {
  const byShape = new Map<string, Set<number>>();
  for (const c of corners) byShape.set(c.shape, (byShape.get(c.shape) ?? new Set()).add(c.index));
  return shapes.map((s) => {
    const idx = byShape.get(s.id);
    if (!idx || !s.points) return s;
    return { ...s, points: s.points.map((q, i) => (idx.has(i) ? ([p[0], p[1]] as Point) : q)) };
  });
}

/** Binds opening `s` to `ref` (its centre at `ref.t`), the centre optionally
 *  snapped along the edge to `grid` and kept so the opening fits the edge. */
export function bindOpening(
  shapes: PlanShape[],
  s: PlanShape,
  ref: WallRef,
  grid: number | null,
): PlanShape {
  const room = shapes.find((r) => r.id === ref.shape && isRoom(r));
  const e = room && edgeOf(room, ref.edge);
  if (!e) return s;
  const len = dist(e[0], e[1]);
  if (!len) return s;
  let t = ref.t;
  if (grid) t = (Math.round((t * len) / grid) * grid) / len;
  const half = Math.min(s.width ?? 0, len) / 2 / len;
  t = clamp(t, half, 1 - half);
  return { ...s, wall: { shape: ref.shape, edge: ref.edge, t: Math.round(t * 1e4) / 1e4 } };
}

/** Centre of a wall-bound opening as drawn. */
export function openingCentre(shapes: PlanShape[], s: PlanShape): Point | null {
  const seg = openingSegment(shapes, s);
  return seg ? lerp(seg.a, seg.b, 0.5) : null;
}

/** Slides opening `s` to the room edge nearest to `target` (its own edge wins
 *  a tie, e.g. on a shared wall). */
export function slideOpeningTo(
  shapes: PlanShape[],
  s: PlanShape,
  target: Point,
  grid: number | null,
): PlanShape {
  let ref: WallRef | null = null;
  const hit = nearestRoomEdge(shapes, target, Infinity);
  if (hit) ref = { shape: hit.shape, edge: hit.edge, t: hit.t };
  const room = s.wall && shapes.find((r) => r.id === s.wall!.shape && isRoom(r));
  const own = room && edgeOf(room, s.wall!.edge);
  if (own) {
    const pr = project(own[0], own[1], target);
    if (!hit || pr.dist <= hit.dist + ON_WALL) ref = { shape: s.wall!.shape, edge: s.wall!.edge, t: pr.t };
  }
  return ref ? bindOpening(shapes, s, ref, grid) : s;
}

/** Moves opening `s` by (dx, dy) projected onto its own edge. */
export function nudgeOpening(shapes: PlanShape[], s: PlanShape, dx: number, dy: number): PlanShape {
  const room = s.wall && shapes.find((r) => r.id === s.wall!.shape && isRoom(r));
  const e = room && edgeOf(room, s.wall!.edge);
  if (!e) return s;
  const len = dist(e[0], e[1]);
  if (!len) return s;
  const along = (dx * (e[1][0] - e[0][0]) + dy * (e[1][1] - e[0][1])) / len;
  const c = openingCentre(shapes, s);
  const t0 = c ? project(e[0], e[1], c).t : s.wall!.t;
  return bindOpening(shapes, s, { ...s.wall!, t: t0 + along / len }, null);
}

/** Inserts corner `p` into every room edge running through it (a shared wall
 *  gets the corner in both rooms, so it moves as one), except where `p` lies
 *  within `minGap` of an existing corner. Returns the new shapes and the
 *  inserted corners. */
export function insertCornerAt(
  shapes: PlanShape[],
  p: Point,
  minGap: number,
): { shapes: PlanShape[]; inserted: { shape: string; index: number }[] } {
  let out = shapes;
  const inserted: { shape: string; index: number }[] = [];
  for (const room of shapes) {
    if (!isRoom(room)) continue;
    const n = ptsOf(room).length;
    let best: { edge: number; dist: number } | null = null;
    for (let i = 0; i < n; i++) {
      const e = edgeOf(room, i);
      if (!e || dist(e[0], p) <= minGap || dist(e[1], p) <= minGap) continue;
      const pr = project(e[0], e[1], p);
      if (pr.dist <= ON_WALL && (!best || pr.dist < best.dist)) best = { edge: i, dist: pr.dist };
    }
    if (!best) continue;
    out = insertCorner(out, room.id, best.edge, p);
    inserted.push({ shape: room.id, index: best.edge + 1 });
  }
  return { shapes: out, inserted };
}

/** Default width of a new door / window: 0.90 m / 1.20 m with a scale, else
 *  45 / 60 plan units. */
export function defaultOpeningWidth(type: "door" | "window", scale: number | null | undefined): number {
  return round1(scale ? (type === "door" ? 0.9 : 1.2) * scale : type === "door" ? 45 : 60);
}
