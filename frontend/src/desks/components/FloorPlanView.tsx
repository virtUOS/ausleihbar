// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { Accessibility, Mars, Maximize, Minus, Plus, Venus, type LucideIcon } from "lucide-react";
import type { PlanShape, PlanSymbol, PlaceKind, RoomIcon } from "../types";
import { stateLabel, stateMeta, type DrawState } from "./placeStates";
import { DayLoadSvg } from "./DayLoadBar";
import { dayLoadText, type DayLoad } from "../dayLoad";
import { clampView, MAX_ZOOM, symbolSize, symbolUnit, zoomViewAbout, type View } from "./planGeometry";
import { centroid, type Point } from "./planEditorState";
import { doorGeometry, openingSegment, wallSegments } from "./planWalls";

/** Largest on-screen size of one symbol unit (CSS px) the viewer zooms to. */
const MAX_UNIT_PX = 28;
/** The zoom limit never goes below this (tiny plans on big screens). */
const MIN_MAX_ZOOM = 1.5;

/** A place to draw on the plan. */
export interface PlanPlace {
  id: number;
  name: string;
  kind: PlaceKind;
  symbol: PlanSymbol | null;
  state: DrawState;
  /** Holder is the viewer — drawn with an extra green frame. */
  mine?: boolean;
  /** Morning / afternoon load of the day, drawn above the symbol. */
  load?: DayLoad;
}

interface Props {
  shapes: PlanShape[];
  places: PlanPlace[];
  /** Plan coordinates per metre (Floor.scale_px_per_m); sizes the symbols. */
  scalePxPerM?: number | null;
  selectedIds?: number[];
  onPlaceClick?: (id: number) => void;
  /** Overrides the accessible name suffix, default: the state label. */
  describe?: (p: PlanPlace) => string;
  className?: string;
  /** Draw place names next to the symbols (readable once zoomed in). */
  showNames?: boolean;
}

const pointsOf = (s: PlanShape) => (s.points ?? []).filter((p) => p.length >= 2);

/** Pure SVG renderer of a floor plan (rooms, walls, doors, labels) with the
 *  place symbols on top, plus pinch/wheel zoom and drag pan. Rendering
 *  (`PlanDrawing`) is kept apart from the interaction so the plan editor can
 *  reuse the drawing. No `style=` attributes (CSP). */
export function FloorPlanView({
  shapes,
  places,
  scalePxPerM,
  selectedIds,
  onPlaceClick,
  describe,
  className = "",
  showNames = true,
}: Props) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const [focusId, setFocusId] = useState<number | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const moved = useRef(false);
  const downAt = useRef<{ x: number; y: number } | null>(null);

  const geo = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const s of shapes) for (const [x, y] of pointsOf(s)) (xs.push(x), ys.push(y));
    for (const p of places) if (p.symbol) (xs.push(p.symbol.x), ys.push(p.symbol.y));
    if (xs.length === 0) return null;
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const w0 = Math.max(Math.max(...xs) - minX, 1);
    const h0 = Math.max(Math.max(...ys) - minY, 1);
    const diag = Math.hypot(w0, h0);
    const u = symbolUnit(diag, scalePxPerM);
    const pad = u * 2.5;
    return { minX, minY, u, pad, W: w0 + pad * 2, H: h0 + pad * 2 };
  }, [shapes, places, scalePxPerM]);

  // Zooming further does not add detail, it only loses the overview: stop
  // once a symbol unit (about 0.45 m, a desk is a few units wide) is
  // MAX_UNIT_PX on screen — adapts to plan size and screen width.
  const basePx = geo && box.w > 0 ? Math.min(box.w / geo.W, box.h / geo.H || Infinity) : 0;
  const maxZoom = geo && basePx > 0 ? Math.min(MAX_ZOOM, Math.max(MIN_MAX_ZOOM, MAX_UNIT_PX / (geo.u * basePx))) : MAX_ZOOM;
  const maxZoomRef = useRef(maxZoom);
  maxZoomRef.current = maxZoom;
  // A smaller viewport (rotation, resize) lowers the limit: pull the view in.
  useEffect(() => {
    if (geo && viewRef.current.k > maxZoom) setView((v) => clampView(v, geo.W, geo.H, maxZoom));
  }, [geo, maxZoom]);

  const clamp = (v: View, W: number, H: number): View => clampView(v, W, H, maxZoomRef.current);

  /** Client pixel → view units (viewBox 0 0 W H, preserveAspectRatio meet). */
  function toView(cx: number, cy: number) {
    const rect = svgRef.current!.getBoundingClientRect();
    const r = Math.max(geo!.W / rect.width, geo!.H / rect.height);
    const offX = (rect.width - geo!.W / r) / 2;
    const offY = (rect.height - geo!.H / r) / 2;
    return { x: (cx - rect.left - offX) * r, y: (cy - rect.top - offY) * r, r };
  }

  function zoomAbout(v: View, factor: number, fx: number, fy: number): View {
    return zoomViewAbout(v, factor, fx, fy, geo!.W, geo!.H, maxZoomRef.current);
  }

  // Wheel zoom needs a non-passive listener to stop the page from scrolling.
  useEffect(() => {
    const el = svgRef.current;
    if (!el || !geo) return;
    const onWheel = (e: WheelEvent) => {
      // At minimum zoom, scrolling/zooming out passes through to the page.
      if (e.deltaY > 0 && viewRef.current.k <= 1) return;
      e.preventDefault();
      const p = toView(e.clientX, e.clientY);
      setView((v) => zoomAbout(v, Math.exp(-e.deltaY * 0.0015), p.x, p.y));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo]);

  /** Half the distance to the nearest other symbol: caps the hit radius. */
  const nearest = useMemo(() => {
    const pl = places.filter((p) => p.symbol);
    const m = new Map<number, number>();
    for (const a of pl) {
      let d = Infinity;
      for (const b of pl) {
        if (a !== b) d = Math.min(d, Math.hypot(a.symbol!.x - b.symbol!.x, a.symbol!.y - b.symbol!.y));
      }
      m.set(a.id, d / 2);
    }
    return m;
  }, [places]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el || !geo) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setBox((b) => (Math.abs(b.w - r.width) < 1 && Math.abs(b.h - r.height) < 1 ? b : { w: r.width, h: r.height }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [geo]);

  if (!geo) return null;

  /** CSS pixels per plan unit at the current zoom. */
  const pxPerUnit = box.w > 0 ? Math.min(box.w / geo.W, box.h / geo.H || Infinity) * view.k : 0;
  // Hit area of at least 22 CSS px radius (44 px target), whatever the zoom.
  const hitR = Math.max(geo.u * 1.6, pxPerUnit > 0 ? 22 / pxPerUnit : 0);

  function revealSymbol(sym: PlanSymbol) {
    setView((v) => {
      const sx = v.x + (sym.x - geo!.minX + geo!.pad) * v.k;
      const sy = v.y + (sym.y - geo!.minY + geo!.pad) * v.k;
      const m = geo!.u * 2;
      if (sx >= m && sx <= geo!.W - m && sy >= m && sy <= geo!.H - m) return v;
      return clamp(
        {
          k: v.k,
          x: geo!.W / 2 - (sym.x - geo!.minX + geo!.pad) * v.k,
          y: geo!.H / 2 - (sym.y - geo!.minY + geo!.pad) * v.k,
        },
        geo!.W,
        geo!.H,
      );
    });
  }

  function onPointerDown(e: PointerEvent<SVGSVGElement>) {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 1) {
      moved.current = false;
      downAt.current = { x: e.clientX, y: e.clientY };
    } else {
      moved.current = true;
    }
  }

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    const cur = { x: e.clientX, y: e.clientY };
    if (pointers.current.size >= 2) {
      const others = [...pointers.current.entries()].filter(([id]) => id !== e.pointerId);
      const o = others[0][1];
      const d0 = Math.hypot(prev.x - o.x, prev.y - o.y) || 1;
      const d1 = Math.hypot(cur.x - o.x, cur.y - o.y);
      const mid0 = { x: (prev.x + o.x) / 2, y: (prev.y + o.y) / 2 };
      const mid1 = { x: (cur.x + o.x) / 2, y: (cur.y + o.y) / 2 };
      const p0 = toView(mid0.x, mid0.y);
      const p1 = toView(mid1.x, mid1.y);
      setView((v) => {
        const z = zoomAbout(v, d1 / d0, p0.x, p0.y);
        return clamp({ ...z, x: z.x + (p1.x - p0.x), y: z.y + (p1.y - p0.y) }, geo!.W, geo!.H);
      });
    } else {
      if (!moved.current) {
        const d = downAt.current!;
        if (Math.hypot(cur.x - d.x, cur.y - d.y) < 6) return;
        moved.current = true;
        try {
          e.currentTarget.setPointerCapture(e.pointerId);
        } catch {
          // synthetic pointers cannot be captured — dragging still works
        }
      }
      const r = toView(0, 0).r;
      const dx = (cur.x - prev.x) * r;
      const dy = (cur.y - prev.y) * r;
      setView((v) => clamp({ ...v, x: v.x + dx, y: v.y + dy }, geo!.W, geo!.H));
    }
    pointers.current.set(e.pointerId, cur);
  }

  function onPointerUp(e: PointerEvent<SVGSVGElement>) {
    pointers.current.delete(e.pointerId);
  }

  function step(factor: number) {
    setView((v) => zoomAbout(v, factor, geo!.W / 2, geo!.H / 2));
  }

  const btn =
    "flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 bg-white/95 text-slate-800 shadow-sm hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800/95 dark:text-slate-100 dark:hover:bg-slate-700";
  const { u } = geo;

  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 ${className}`}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${geo.W} ${geo.H}`}
        role="group"
        aria-label={t("Floor plan")}
        className={`block h-auto max-h-[70vh] min-h-[200px] w-full select-none ${view.k > 1 ? "touch-none" : "touch-pan-y"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClickCapture={(e) => {
          if (moved.current) {
            e.stopPropagation();
            moved.current = false;
          }
        }}
      >
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          <g transform={`translate(${geo.pad - geo.minX} ${geo.pad - geo.minY})`}>
            <PlanDrawing shapes={shapes} u={u} scale={scalePxPerM} />
            {/* Hit layer below every symbol body: enlarged touch targets that
                never cover a neighbour (radius capped at half the distance to it). */}
            {onPlaceClick &&
              places
                .filter((p) => p.symbol)
                .map((p) => {
                  const body = p.kind === "meeting_room" ? u * 1.5 : u;
                  const r = Math.max(body, Math.min(hitR, nearest.get(p.id) ?? hitR));
                  return (
                    <circle
                      key={`hit-${p.id}`}
                      cx={p.symbol!.x}
                      cy={p.symbol!.y}
                      r={r}
                      aria-hidden
                      className="cursor-pointer fill-transparent"
                      onClick={() => onPlaceClick(p.id)}
                    />
                  );
                })}
            {places
              .filter((p) => p.symbol)
              .map((p) => {
                const meta = stateMeta(p.state);
                const sel = selectedIds?.includes(p.id) ?? false;
                const { w, h } = symbolSize(p.kind, u);
                const label = [
                  `${p.name}: ${describe ? describe(p) : stateLabel(t, p.state)}`,
                  p.load ? dayLoadText(t, p.load) : "",
                ]
                  .filter(Boolean)
                  .join(", ");
                const interactive = !!onPlaceClick;
                const act = () => onPlaceClick?.(p.id);
                return (
                  <g
                    key={p.id}
                    transform={`translate(${p.symbol!.x} ${p.symbol!.y})`}
                    role={interactive ? "button" : "img"}
                    tabIndex={interactive ? 0 : undefined}
                    aria-label={label}
                    aria-pressed={interactive && selectedIds !== undefined ? sel : undefined}
                    className={interactive ? "cursor-pointer" : ""}
                    onClick={act}
                    onFocus={(e) => {
                      setFocusId(p.id);
                      // Pan only for keyboard focus; a pointer press must not move the view.
                      if (e.currentTarget.matches(":focus-visible")) revealSymbol(p.symbol!);
                    }}
                    onBlur={() => setFocusId((f) => (f === p.id ? null : f))}
                    onKeyDown={(e: KeyboardEvent<SVGGElement>) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        act();
                      }
                    }}
                  >
                    {(sel || focusId === p.id || p.mine) && (
                      <rect
                        x={-w / 2 - u * 0.35}
                        y={-h / 2 - u * 0.35}
                        width={w + u * 0.7}
                        height={h + u * 0.7}
                        rx={u * 0.6}
                        transform={`rotate(${p.symbol!.rotation || 0})`}
                        strokeWidth={focusId === p.id ? 3 : 2.5}
                        vectorEffect="non-scaling-stroke"
                        className={
                          focusId === p.id
                            ? "fill-none stroke-brand-600 dark:stroke-brand-300"
                            : sel
                              ? "fill-brand-200/60 stroke-brand-600 dark:fill-brand-400/30 dark:stroke-brand-300"
                              : "fill-none stroke-green-600 dark:stroke-green-400"
                        }
                      />
                    )}
                    {p.load && <DayLoadSvg load={p.load} r={Math.max(w, h) / 2 + u * 0.3} />}
                    <PlaceSymbolBody
                      kind={p.kind}
                      rotation={p.symbol!.rotation}
                      u={u}
                      body={meta.body}
                      ink={meta.ink}
                      glyph={meta.glyph}
                      dash={meta.dash}
                      name={showNames ? p.name : undefined}
                    />
                  </g>
                );
              })}
          </g>
        </g>
      </svg>
      <div className="absolute right-2 top-2 flex flex-col gap-2">
        <button
          type="button"
          aria-label={t("Zoom in")}
          disabled={view.k >= maxZoom - 1e-6}
          onClick={() => step(1.5)}
          className={`${btn} disabled:cursor-not-allowed disabled:opacity-40`}
        >
          <Plus aria-hidden className="h-5 w-5" />
        </button>
        <button
          type="button"
          aria-label={t("Zoom out")}
          disabled={view.k <= 1 + 1e-6}
          onClick={() => step(1 / 1.5)}
          className={`${btn} disabled:cursor-not-allowed disabled:opacity-40`}
        >
          <Minus aria-hidden className="h-5 w-5" />
        </button>
        <button
          type="button"
          aria-label={t("Fit to screen")}
          title={t("Fit to screen")}
          onClick={() => setView({ k: 1, x: 0, y: 0 })}
          className={btn}
        >
          <Maximize aria-hidden className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

/** Stairs glyph (no lucide icon): steps rising to the right, 24×24 like lucide. */
function StairsIcon(props: { x: number; y: number; size: number; className?: string }) {
  return (
    <svg
      x={props.x}
      y={props.y}
      width={props.size}
      height={props.size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={props.className}
    >
      <path d="M3 21h5v-5h5v-5h5V6h3" />
      <path d="M3 21V3" />
    </svg>
  );
}

const ROOM_ICONS: Record<RoomIcon, { icon: LucideIcon | null; label: string }> = {
  stairs: { icon: null, label: "Stairs" },
  wc_men: { icon: Mars, label: "Men's toilet" },
  wc_women: { icon: Venus, label: "Women's toilet" },
  wc_accessible: { icon: Accessibility, label: "Accessible toilet" },
};

const linePts = (pts: Point[]) => pts.map((p) => p.join(",")).join(" ");

/** The static drawing of a plan: rooms (walls with door/window gaps for
 *  rooms with `outline: "wall"`), free walls, doors, windows, room icons and
 *  labels. `scale` (plan units per metre) sizes the window depth. */
export function PlanDrawing({
  shapes,
  u,
  scale,
}: {
  shapes: PlanShape[];
  u: number;
  scale?: number | null;
}) {
  const { t } = useTranslation();
  const rooms = shapes.filter((s) => s.type === "room");
  const windowDepth = scale ? scale * 0.15 : 6;
  const wall = "stroke-slate-600 dark:stroke-slate-300";
  return (
    <>
      {rooms.map((s) => (
        <polygon
          key={s.id}
          points={linePts(pointsOf(s) as Point[])}
          strokeWidth={s.outline === "wall" ? 0 : 1}
          vectorEffect="non-scaling-stroke"
          className={
            s.outline === "wall"
              ? "fill-slate-100/70 stroke-none dark:fill-slate-800/60"
              : "fill-slate-100/70 stroke-slate-300 dark:fill-slate-800/60 dark:stroke-slate-600"
          }
        />
      ))}
      {rooms
        .filter((s) => s.outline === "wall")
        .flatMap((s) =>
          wallSegments(shapes, s).map(([a, b], i) => (
            <line
              key={`${s.id}-w${i}`}
              x1={a[0]}
              y1={a[1]}
              x2={b[0]}
              y2={b[1]}
              strokeWidth={3}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              className={wall}
            />
          )),
        )}
      {shapes
        .filter((s) => s.type === "wall")
        .map((s) => (
          <polyline
            key={s.id}
            points={pointsOf(s).map((p) => p.join(",")).join(" ")}
            fill="none"
            strokeWidth={3}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
            className={wall}
          />
        ))}
      {shapes
        .filter((s) => s.type === "door" && !s.wall)
        .map((s) => (
          <polyline
            key={s.id}
            points={pointsOf(s).map((p) => p.join(",")).join(" ")}
            fill="none"
            strokeWidth={4}
            strokeDasharray="6 3"
            vectorEffect="non-scaling-stroke"
            className="stroke-brand-600 dark:stroke-brand-400"
          />
        ))}
      {shapes
        .filter((s) => s.type === "window")
        .map((s) => {
          const seg = openingSegment(shapes, s);
          if (!seg) return null;
          const { a, b } = seg;
          const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
          const h = windowDepth / 2;
          const nx = (-(b[1] - a[1]) / len) * h;
          const ny = ((b[0] - a[0]) / len) * h;
          return (
            <g key={s.id}>
              <polygon
                points={linePts([
                  [a[0] + nx, a[1] + ny],
                  [b[0] + nx, b[1] + ny],
                  [b[0] - nx, b[1] - ny],
                  [a[0] - nx, a[1] - ny],
                ])}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
                className={`fill-white dark:fill-slate-900 ${wall}`}
              />
              <line
                x1={a[0]}
                y1={a[1]}
                x2={b[0]}
                y2={b[1]}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
                className={wall}
              />
            </g>
          );
        })}
      {shapes
        .filter((s) => s.type === "door" && s.wall)
        .map((s) => {
          const d = doorGeometry(shapes, s);
          if (!d) return null;
          return (
            <g key={s.id} fill="none">
              <line
                x1={d.hinge[0]}
                y1={d.hinge[1]}
                x2={d.leaf[0]}
                y2={d.leaf[1]}
                strokeWidth={2}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                className={wall}
              />
              <path
                d={`M ${d.leaf[0]} ${d.leaf[1]} A ${d.r} ${d.r} 0 0 ${d.sweep} ${d.free[0]} ${d.free[1]}`}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
                className="stroke-slate-500 dark:stroke-slate-400"
              />
            </g>
          );
        })}
      {rooms
        .filter((s) => s.icon && ROOM_ICONS[s.icon] && pointsOf(s).length)
        .map((s) => {
          const { icon: Icon, label } = ROOM_ICONS[s.icon!];
          const [cx, cy] = centroid(pointsOf(s) as Point[]);
          const size = u * 1.6;
          const box = { x: cx - size / 2, y: cy - size / 2 };
          const ink = "text-slate-500 dark:text-slate-400";
          return (
            <g key={`icon-${s.id}`}>
              <title>{t(label)}</title>
              {Icon ? (
                <Icon aria-hidden x={box.x} y={box.y} width={size} height={size} className={ink} />
              ) : (
                <StairsIcon x={box.x} y={box.y} size={size} className={ink} />
              )}
            </g>
          );
        })}
      {shapes
        .filter((s) => s.type === "label" && s.text && pointsOf(s)[0])
        .map((s) => {
          const [x, y] = pointsOf(s)[0];
          return (
            <text
              key={s.id}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={u * 0.9}
              fontWeight={600}
              className="pointer-events-none fill-slate-700 dark:fill-slate-200"
            >
              {s.text}
            </text>
          );
        })}
    </>
  );
}

/** The drawn body of a place symbol around (0, 0): rotated rectangle, glyph
 *  and optional name below. Shared by the viewer and the plan editor. */
export function PlaceSymbolBody({
  kind,
  rotation,
  u,
  body,
  ink,
  glyph,
  dash,
  name,
}: {
  kind: PlaceKind;
  rotation: number;
  u: number;
  body: string;
  ink: string;
  glyph: string;
  dash?: string;
  name?: string;
}) {
  const room = kind === "meeting_room";
  const { w, h } = symbolSize(kind, u);
  return (
    <>
      <rect
        x={-w / 2}
        y={-h / 2}
        width={w}
        height={h}
        rx={room ? u * 0.5 : u}
        transform={`rotate(${rotation || 0})`}
        strokeWidth={1.75}
        strokeDasharray={dash}
        vectorEffect="non-scaling-stroke"
        className={body}
      />
      <text
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={u * 1.1}
        fontWeight={700}
        className={`pointer-events-none ${ink}`}
      >
        {glyph}
      </text>
      {name !== undefined && (
        <text
          y={h / 2 + u * 0.9}
          textAnchor="middle"
          fontSize={u * 0.7}
          strokeWidth={3}
          paintOrder="stroke"
          vectorEffect="non-scaling-stroke"
          className="pointer-events-none fill-slate-800 stroke-white dark:fill-slate-100 dark:stroke-slate-900"
        >
          {name}
        </text>
      )}
    </>
  );
}
