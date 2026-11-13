// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { PointerEvent as ReactPointerEvent, Ref } from "react";
import { useTranslation } from "react-i18next";
import type { Place, PlanShape, PlanSymbol } from "../types";
import { PlaceSymbolBody, PlanDrawing } from "./FloorPlanView";
import { symbolSize, type View } from "./planGeometry";
import { centroid, type Point } from "./planEditorState";

export type EditorTool = "select" | "room" | "wall" | "door" | "label" | "place" | "scale";

export type Selection = { kind: "shape"; id: string } | { kind: "symbol"; id: number } | null;

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
  scaleBar: { m: number; width: number } | null;
  onPointerDown: (e: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerMove: (e: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerUp: () => void;
  onPointerLeave: () => void;
  onDoubleClick: () => void;
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
  const selectedPoints =
    selectedShape && selectedShape.type !== "label" ? pointsOf(selectedShape) : [];
  const accent = "pointer-events-none stroke-brand-600 dark:stroke-brand-300";

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
            <PlanDrawing shapes={shapes} u={u} />

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
              ["room", "wall", "door", "label"].flatMap((type) =>
                shapes
                  .filter((s) => s.type === type)
                  .map((s) => {
                    const pts = pointsOf(s);
                    const common = { "data-hit": "shape", "data-id": s.id, className: "cursor-move" };
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
            {selectedShape && selectedShape.type !== "label" && (
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
                  className="cursor-grab fill-white stroke-brand-600 dark:fill-slate-900 dark:stroke-brand-300"
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
            {(tool === "door" || tool === "scale") && draft.length > 0 && (
              <polyline
                points={[...draft, ...(draft.length === 1 && cursor ? [cursor] : [])]
                  .map((p) => p.join(","))
                  .join(" ")}
                fill="none"
                strokeWidth={tool === "scale" ? 2 : 4}
                strokeDasharray={tool === "scale" ? undefined : "6 3"}
                vectorEffect="non-scaling-stroke"
                className={accent}
              />
            )}
            {(tool === "room" || tool === "wall" || tool === "door" || tool === "scale") &&
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
            {cursor && tool !== "select" && tool !== "label" && (
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
