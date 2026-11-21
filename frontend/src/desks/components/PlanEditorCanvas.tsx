// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, Ref } from "react";
import { useTranslation } from "react-i18next";
import type { Place, PlanShape, PlanSymbol } from "../types";
import { PlaceSymbolBody, PlanDrawing } from "./FloorPlanView";
import { symbolSize, type View } from "./planGeometry";
import { centroid, type Point } from "./planEditorState";
import { doorGeometry, openingSegment } from "./planWalls";

export type EditorTool =
  | "select"
  | "rect"
  | "room"
  | "wall"
  | "insert"
  | "door"
  | "window"
  | "label"
  | "place"
  | "scale";

/** A selected shape (with `vertex`: one of its room corners) or symbol. */
export type Selection =
  | { kind: "shape"; id: string; vertex?: number }
  | { kind: "symbol"; id: number }
  | null;

export interface PlanTemplate {
  url: string;
  width: number;
  height: number;
}

const pointsOf = (s: PlanShape) => (s.points ?? []) as Point[];

/** Width of a label's (approximate) hit box from its character count. */
const labelWidth = (s: PlanShape, u: number) => Math.max(1, (s.text ?? "").length) * u * 0.55 + u;

interface Props {
  svgRef: Ref<SVGSVGElement>;
  contentRef: Ref<SVGGElement>;
  /** Prefix of element ids (grid pattern, description). */
  uid: string;
  describedBy: string;
  W: number;
  H: number;
  view: View;
  /** Symbol unit (see `symbolUnit`). */
  u: number;
  /** Plan units per metre (null: not set); sizes window depths. */
  scale?: number | null;
  grid: number;
  showGrid: boolean;
  /** Plan units → screen pixels at the current zoom (0 = not measured yet). */
  pxPerUnit: number;
  template: PlanTemplate | null;
  opacity: number;
  shapes: PlanShape[];
  places: Place[];
  symbols: Record<number, PlanSymbol | null>;
  roomName: (roomId: number | null | undefined) => string | null;
  tool: EditorTool;
  selection: Selection;
  draft: Point[];
  cursor: Point | null;
  pendingLabel: Point | null;
  /** Door/window about to be placed (door and window tools). */
  preview: PlanShape | null;
  scaleBar: { m: number; width: number } | null;
  onPointerDown: (e: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerMove: (e: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerUp: () => void;
  onPointerLeave: () => void;
  onDoubleClick: (e: ReactMouseEvent<SVGSVGElement>) => void;
}

/** The drawing surface of the plan editor: template, grid, the plan (shared
 *  `PlanDrawing`), hit areas, place symbols, selection and drawing previews.
 *  Pure rendering; the editor shell owns state and pointer logic. */
export function PlanEditorCanvas(props: Props) {
  const { t } = useTranslation();
  const {
    W,
    H,
    view,
    u,
    grid,
    pxPerUnit,
    template,
    shapes,
    places,
    symbols,
    tool,
    selection,
    draft,
    cursor,
    pendingLabel,
    uid,
  } = props;
  const px = (n: number) => (pxPerUnit > 0 ? n / pxPerUnit : n);
  const selectedShape =
    selection?.kind === "shape" ? shapes.find((s) => s.id === selection.id) : undefined;
  /** A wall-bound door/window: no points, drawn from its wall. */
  const selectedOpening = selectedShape?.wall ? openingSegment(shapes, selectedShape) : null;
  const selectedPoints =
    selectedShape && selectedShape.type !== "label" && !selectedShape.wall ? pointsOf(selectedShape) : [];
  const selectedVertex = selection?.kind === "shape" ? selection.vertex : undefined;
  const accent = "pointer-events-none stroke-brand-600 dark:stroke-brand-300";
  const preview = props.preview;
  const previewSeg = preview ? openingSegment([...shapes, preview], preview) : null;
  const previewDoor = preview?.type === "door" ? doorGeometry([...shapes, preview], preview) : null;

  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900">
      <svg
        ref={props.svgRef}
        viewBox={`0 0 ${W} ${H}`}
        role="application"
        tabIndex={0}
        aria-label={t("Floor plan editor")}
        aria-describedby={props.describedBy}
        className={`block h-[70vh] w-full touch-none select-none rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-600 ${
          tool === "select" ? "cursor-default" : "cursor-crosshair"
        }`}
        onPointerDown={props.onPointerDown}
        onPointerMove={props.onPointerMove}
        onPointerUp={props.onPointerUp}
        onPointerCancel={props.onPointerUp}
        onPointerLeave={props.onPointerLeave}
        onDoubleClick={props.onDoubleClick}
      >
        <defs>
          <pattern id={`${uid}-grid`} width={grid} height={grid} patternUnits="userSpaceOnUse">
            <path
              d={`M ${grid} 0 L 0 0 0 ${grid}`}
              fill="none"
              strokeWidth={0.5}
              vectorEffect="non-scaling-stroke"
              className="stroke-slate-300 dark:stroke-slate-700"
            />
          </pattern>
        </defs>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          <g ref={props.contentRef}>
            <rect x={0} y={0} width={W} height={H} className="fill-white dark:fill-slate-950" />
            {template && (
              <image
                href={template.url}
                x={0}
                y={0}
                width={template.width}
                height={template.height}
                opacity={props.opacity / 100}
                preserveAspectRatio="none"
                pointerEvents="none"
              />
            )}
            {props.showGrid && (
              <rect x={0} y={0} width={W} height={H} fill={`url(#${uid}-grid)`} pointerEvents="none" />
            )}
            <PlanDrawing shapes={shapes} u={u} scale={props.scale} />

            {/* Linked room names (editor only). */}
            {shapes
              .filter((s) => s.type === "room" && props.roomName(s.room_id))
              .map((s) => {
                const [x, y] = centroid(pointsOf(s));
                return (
                  <text
                    key={`rn-${s.id}`}
                    x={x}
                    y={y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={u * 0.7}
                    className="pointer-events-none fill-slate-500 italic dark:fill-slate-400"
                  >
                    {props.roomName(s.room_id)}
                  </text>
                );
              })}

            {/* Hit areas of the shapes (selection). */}
            {tool === "select" &&
              ["room", "wall", "door", "window", "label"].flatMap((type) =>
                shapes
                  .filter((s) => s.type === type)
                  .map((s) => {
                    const pts = pointsOf(s);
                    const common = { "data-hit": "shape", "data-id": s.id, className: "cursor-move" };
                    if (s.wall) {
                      // Wall-bound door/window: a band along its opening.
                      const seg = openingSegment(shapes, s);
                      if (!seg) return null;
                      return (
                        <line
                          key={`hit-${s.id}`}
                          {...common}
                          x1={seg.a[0]}
                          y1={seg.a[1]}
                          x2={seg.b[0]}
                          y2={seg.b[1]}
                          stroke="transparent"
                          strokeWidth={16}
                          vectorEffect="non-scaling-stroke"
                          pointerEvents="stroke"
                        />
                      );
                    }
                    if (s.type === "room")
                      return (
                        <polygon
                          key={`hit-${s.id}`}
                          {...common}
                          points={pts.map((p) => p.join(",")).join(" ")}
                          fill="transparent"
                          pointerEvents="all"
                        />
                      );
                    if (s.type === "label") {
                      if (!pts[0]) return null;
                      const w = labelWidth(s, u);
                      return (
                        <rect
                          key={`hit-${s.id}`}
                          {...common}
                          x={pts[0][0] - w / 2}
                          y={pts[0][1] - u * 0.7}
                          width={w}
                          height={u * 1.4}
                          fill="transparent"
                          pointerEvents="all"
                        />
                      );
                    }
                    return (
                      <polyline
                        key={`hit-${s.id}`}
                        {...common}
                        points={pts.map((p) => p.join(",")).join(" ")}
                        fill="none"
                        stroke="transparent"
                        strokeWidth={16}
                        vectorEffect="non-scaling-stroke"
                        pointerEvents="stroke"
                      />
                    );
                  }),
              )}

            {/* Place symbols. */}
            {places
              .filter((p) => symbols[p.id])
              .map((p) => {
                const sym = symbols[p.id]!;
                const sel = selection?.kind === "symbol" && selection.id === p.id;
                const { w, h } = symbolSize(p.kind, u);
                return (
                  <g
                    key={`sym-${p.id}`}
                    transform={`translate(${sym.x} ${sym.y})`}
                    data-hit="symbol"
                    data-id={p.id}
                    className={tool === "select" ? "cursor-move" : "pointer-events-none"}
                  >
                    {sel && (
                      <rect
                        x={-w / 2 - u * 0.35}
                        y={-h / 2 - u * 0.35}
                        width={w + u * 0.7}
                        height={h + u * 0.7}
                        rx={u * 0.6}
                        transform={`rotate(${sym.rotation || 0})`}
                        strokeWidth={2.5}
                        vectorEffect="non-scaling-stroke"
                        className="fill-brand-200/60 stroke-brand-600 dark:fill-brand-400/30 dark:stroke-brand-300"
                      />
                    )}
                    <PlaceSymbolBody
                      kind={p.kind}
                      rotation={sym.rotation}
                      u={u}
                      body="fill-white stroke-slate-700 dark:fill-slate-800 dark:stroke-slate-200"
                      ink="fill-slate-700 dark:fill-slate-200"
                      glyph=""
                      name={p.name}
                    />
                    {/* Front edge marker: shows the rotation. */}
                    <line
                      x1={-w / 4}
                      x2={w / 4}
                      y1={h / 2}
                      y2={h / 2}
                      transform={`rotate(${sym.rotation || 0})`}
                      strokeWidth={3}
                      vectorEffect="non-scaling-stroke"
                      className={accent}
                    />
                  </g>
                );
              })}

            {/* Selected shape: outline and vertex handles. */}
            {selectedOpening && (
              <line
                x1={selectedOpening.a[0]}
                y1={selectedOpening.a[1]}
                x2={selectedOpening.b[0]}
                y2={selectedOpening.b[1]}
                strokeWidth={8}
                strokeLinecap="round"
                strokeOpacity={0.6}
                vectorEffect="non-scaling-stroke"
                className={accent}
              />
            )}
            {selectedShape && selectedShape.type !== "label" && !selectedShape.wall && (
              <polyline
                points={[
                  ...selectedPoints,
                  ...(selectedShape.type === "room" ? selectedPoints.slice(0, 1) : []),
                ]
                  .map((p) => p.join(","))
                  .join(" ")}
                fill="none"
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
                className={accent}
              />
            )}
            {selectedShape?.type === "label" && pointsOf(selectedShape)[0] && (
              <rect
                x={pointsOf(selectedShape)[0][0] - labelWidth(selectedShape, u) / 2}
                y={pointsOf(selectedShape)[0][1] - u * 0.7}
                width={labelWidth(selectedShape, u)}
                height={u * 1.4}
                rx={u * 0.2}
                fill="none"
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
                className={accent}
              />
            )}
            {tool === "select" &&
              selectedShape &&
              selectedPoints.map(([x, y], i) => (
                <circle
                  key={`v-${i}`}
                  cx={x}
                  cy={y}
                  r={px(6)}
                  data-hit="vertex"
                  data-id={selectedShape.id}
                  data-index={i}
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                  className={`cursor-grab stroke-brand-600 dark:stroke-brand-300 ${
                    selectedVertex === i ? "fill-brand-600 dark:fill-brand-300" : "fill-white dark:fill-slate-900"
                  }`}
                />
              ))}

            {/* Drawing previews. */}
            {(tool === "room" || tool === "wall") && draft.length > 0 && (
              <polyline
                points={[
                  ...draft,
                  ...(cursor ? [cursor] : []),
                  ...(tool === "room" && draft.length > 1 ? [draft[0]] : []),
                ]
                  .map((p) => p.join(","))
                  .join(" ")}
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
                className={`${accent} ${tool === "room" ? "fill-brand-200/30" : "fill-none"}`}
              />
            )}
            {tool === "rect" && draft.length === 4 && (
              <polygon
                points={draft.map((p) => p.join(",")).join(" ")}
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
                className={`${accent} fill-brand-200/30`}
              />
            )}
            {tool === "scale" && draft.length > 0 && (
              <polyline
                points={[...draft, ...(draft.length === 1 && cursor ? [cursor] : [])]
                  .map((p) => p.join(","))
                  .join(" ")}
                fill="none"
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
                className={accent}
              />
            )}
            {previewSeg && (
              <g fill="none">
                <line
                  x1={previewSeg.a[0]}
                  y1={previewSeg.a[1]}
                  x2={previewSeg.b[0]}
                  y2={previewSeg.b[1]}
                  strokeWidth={5}
                  vectorEffect="non-scaling-stroke"
                  className={accent}
                />
                {previewDoor && (
                  <>
                    <line
                      x1={previewDoor.hinge[0]}
                      y1={previewDoor.hinge[1]}
                      x2={previewDoor.leaf[0]}
                      y2={previewDoor.leaf[1]}
                      strokeWidth={2}
                      vectorEffect="non-scaling-stroke"
                      className={accent}
                    />
                    <path
                      d={`M ${previewDoor.leaf[0]} ${previewDoor.leaf[1]} A ${previewDoor.r} ${previewDoor.r} 0 0 ${previewDoor.sweep} ${previewDoor.free[0]} ${previewDoor.free[1]}`}
                      strokeWidth={1}
                      strokeDasharray="4 3"
                      vectorEffect="non-scaling-stroke"
                      className={accent}
                    />
                  </>
                )}
              </g>
            )}
            {(tool === "room" || tool === "wall" || tool === "scale") &&
              draft.map(([x, y], i) => (
                <circle
                  key={`d-${i}`}
                  cx={x}
                  cy={y}
                  r={px(4)}
                  className="pointer-events-none fill-brand-600 dark:fill-brand-300"
                />
              ))}
            {pendingLabel && (
              <circle
                cx={pendingLabel[0]}
                cy={pendingLabel[1]}
                r={px(5)}
                className="pointer-events-none fill-brand-600 dark:fill-brand-300"
              />
            )}
            {cursor && tool === "insert" && (
              <circle
                cx={cursor[0]}
                cy={cursor[1]}
                r={px(6)}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
                className="pointer-events-none fill-white stroke-brand-600 dark:fill-slate-900 dark:stroke-brand-300"
              />
            )}
            {cursor && tool !== "select" && tool !== "label" && tool !== "insert" && !preview && (
              <circle cx={cursor[0]} cy={cursor[1]} r={px(3)} className="pointer-events-none fill-slate-500" />
            )}
          </g>
        </g>
      </svg>
      {props.scaleBar && (
        <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-white/90 px-2 py-1 text-xs font-semibold text-slate-800 shadow-sm dark:bg-slate-800/90 dark:text-slate-100">
          <div
            aria-hidden
            className="mb-0.5 h-1.5 border-x-2 border-b-2 border-slate-800 dark:border-slate-100"
            style={{ width: `${props.scaleBar.width}px` }}
          />
          {t("{{m}} m", { m: props.scaleBar.m.toLocaleString() })}
        </div>
      )}
    </div>
  );
}
