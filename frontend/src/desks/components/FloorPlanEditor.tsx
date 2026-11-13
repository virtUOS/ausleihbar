// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import {
  useEffect,
  useId,
  useMemo,
  useReducer,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useTranslation } from "react-i18next";
import {
  Armchair,
  BrickWall,
  DoorOpen,
  Maximize,
  MousePointer2,
  Pentagon,
  Redo2,
  RotateCcw,
  RotateCw,
  Ruler,
  Save,
  Trash2,
  Type,
  Undo2,
  Upload,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { useToast } from "../../components/Toast";
import { useUnsavedChangesGuard } from "../../components/useUnsavedChangesGuard";
import { desksApi } from "../api";
import type { Floor, Place, PlanShape, PlanSymbol, Room } from "../types";
import { PlaceSymbolBody, PlanDrawing } from "./FloorPlanView";
import { clampView, symbolSize, symbolUnit, zoomViewAbout, type View } from "./planGeometry";
import {
  centroid,
  changedSymbolIds,
  dedupePoints,
  gridSize,
  historyReducer,
  newShapeId,
  parseMetres,
  round1,
  snap,
  translateShape,
  type PlanDoc,
  type Point,
} from "./planEditorState";

export type EditorTool = "select" | "room" | "wall" | "door" | "label" | "place" | "scale";

type Selection = { kind: "shape"; id: string } | { kind: "symbol"; id: number } | null;

/** A running pointer gesture on the canvas. */
type Gesture =
  | { kind: "pan"; last: { x: number; y: number } }
  | { kind: "shape"; id: string; start: Point; before: PlanDoc }
  | { kind: "symbol"; id: number; start: Point; origin: PlanSymbol; before: PlanDoc }
  | { kind: "vertex"; id: string; index: number; before: PlanDoc };

export interface PlanTemplate {
  url: string;
  width: number;
  height: number;
}

interface Props {
  floor: Floor;
  /** Rooms of this floor (room shapes link to them). */
  rooms: Room[];
  /** Places in those rooms (symbols link to them). */
  places: Place[];
  template: PlanTemplate | null;
  uploading: boolean;
  onUploadTemplate: (file: File) => void;
}

/** Canvas without a template, in plan units. */
const DEFAULT_CANVAS = { w: 1000, h: 700 };
const MAX_EDITOR_ZOOM = 20;

const pointsOf = (s: PlanShape) => (s.points ?? []) as Point[];

const isTextTarget = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  (el.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName));

/** Floor-plan editor of department admins (spec "Places, rooms, location,
 *  equipment"): the uploaded plan is a scale template in the background; the
 *  admin redraws rooms, walls, doors and labels on top and places the floor's
 *  desks and meeting rooms as symbols. Users only ever see the redrawn plan.
 *  Plan units are the template's pixels (default canvas 1000 × 700 without
 *  one). "Speichern" writes the plan, the scale and every changed symbol. */
export function FloorPlanEditor({ floor, rooms, places, template, uploading, onUploadTemplate }: Props) {
  const { t } = useTranslation();
  const toast = useToast();
  const uid = useId();

  const initial = useMemo<PlanDoc>(
    () => ({
      shapes: floor.plan?.shapes ?? [],
      symbols: Object.fromEntries(places.map((p) => [p.id, p.plan_symbol])),
      scale: floor.scale_px_per_m,
    }),
    // The editor is keyed by floor: the initial document is read once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const [history, dispatch] = useReducer(historyReducer, {
    past: [],
    present: initial,
    future: [],
  });
  const doc = history.present;
  const [saved, setSaved] = useState<PlanDoc>(initial);
  const [saving, setSaving] = useState(false);

  const [tool, setToolState] = useState<EditorTool>("select");
  const [selection, setSelection] = useState<Selection>(null);
  const [draft, setDraftState] = useState<Point[]>([]);
  const draftRef = useRef<Point[]>([]);
  const setDraft = (d: Point[]) => {
    draftRef.current = d;
    setDraftState(d);
  };
  const [cursor, setCursor] = useState<Point | null>(null);
  const [pendingLabel, setPendingLabel] = useState<Point | null>(null);
  const [labelText, setLabelText] = useState("");
  const [pendingPlace, setPendingPlace] = useState<number | null>(null);
  const [metres, setMetres] = useState("");
  const [opacity, setOpacity] = useState(50);
  const [snapOn, setSnapOn] = useState(true);
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const [box, setBox] = useState({ w: 0, h: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  const contentRef = useRef<SVGGElement>(null);
  const gesture = useRef<Gesture | null>(null);
  const labelBefore = useRef<PlanDoc | null>(null);
  const labelInput = useRef<HTMLInputElement>(null);
  const metresInput = useRef<HTMLInputElement>(null);

  // --- Derived ---------------------------------------------------------------

  /** Canvas in plan units: the template's size (or the default), grown to
   *  cover what was drawn before. Fixed while editing so nothing jumps. */
  const canvas = useMemo(() => {
    let w = template?.width ?? DEFAULT_CANVAS.w;
    let h = template?.height ?? DEFAULT_CANVAS.h;
    for (const s of initial.shapes)
      for (const [x, y] of pointsOf(s)) (w = Math.max(w, x + 20), h = Math.max(h, y + 20));
    for (const s of Object.values(initial.symbols))
      if (s) (w = Math.max(w, s.x + 40), h = Math.max(h, s.y + 40));
    return { W: Math.ceil(w), H: Math.ceil(h) };
  }, [template, initial]);
  const { W, H } = canvas;

  /** Symbol unit computed exactly like the viewer (content bounds), so the
   *  editor shows symbols at the size users will see. */
  const u = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const s of doc.shapes) for (const [x, y] of pointsOf(s)) (xs.push(x), ys.push(y));
    for (const s of Object.values(doc.symbols)) if (s) (xs.push(s.x), ys.push(s.y));
    const diag =
      xs.length > 1
        ? Math.hypot(
            Math.max(Math.max(...xs) - Math.min(...xs), 1),
            Math.max(Math.max(...ys) - Math.min(...ys), 1),
          )
        : Math.hypot(W, H);
    return symbolUnit(diag, doc.scale);
  }, [doc.shapes, doc.symbols, doc.scale, W, H]);

  const grid = gridSize(doc.scale);
  const pxPerUnit = box.w > 0 ? Math.min(box.w / W, box.h / H) * view.k : 0;
  const px = (n: number) => (pxPerUnit > 0 ? n / pxPerUnit : n);

  const placeById = useMemo(() => new Map(places.map((p) => [p.id, p])), [places]);
  const roomById = useMemo(() => new Map(rooms.map((r) => [r.id, r])), [rooms]);
  const unplaced = places.filter((p) => !doc.symbols[p.id]);

  const symbolsDirty = changedSymbolIds(doc, saved);
  const shapesDirty = doc.shapes !== saved.shapes;
  const scaleDirty = (doc.scale ?? null) !== (saved.scale ?? null);
  const dirty = shapesDirty || scaleDirty || symbolsDirty.length > 0;
  useUnsavedChangesGuard(dirty);

  const selectedShape =
    selection?.kind === "shape" ? doc.shapes.find((s) => s.id === selection.id) : undefined;
  const selectedSymbol = selection?.kind === "symbol" ? doc.symbols[selection.id] : undefined;

  // Drop a selection whose object vanished (undo, delete).
  useEffect(() => {
    if (selection?.kind === "shape" && !selectedShape) setSelection(null);
    if (selection?.kind === "symbol" && !selectedSymbol) setSelection(null);
  }, [selection, selectedShape, selectedSymbol]);

  // --- Document helpers -----------------------------------------------------

  const commit = (next: PlanDoc) => dispatch({ type: "commit", doc: next });
  const replaceShape = (base: PlanDoc, id: string, fn: (s: PlanShape) => PlanShape): PlanDoc => ({
    ...base,
    shapes: base.shapes.map((s) => (s.id === id ? fn(s) : s)),
  });
  const setSymbol = (base: PlanDoc, id: number, sym: PlanSymbol | null): PlanDoc => ({
    ...base,
    symbols: { ...base.symbols, [id]: sym },
  });

  const snapPoint = (p: Point, free = false): Point => snap(p, snapOn && !free ? grid : null);

  function deleteSelection() {
    if (selection?.kind === "shape") {
      commit({ ...doc, shapes: doc.shapes.filter((s) => s.id !== selection.id) });
    } else if (selection?.kind === "symbol") {
      commit(setSymbol(doc, selection.id, null));
    }
    setSelection(null);
  }

  function nudge(dx: number, dy: number) {
    if (selection?.kind === "shape" && selectedShape) {
      commit(replaceShape(doc, selection.id, (s) => translateShape(s, dx, dy)));
    } else if (selection?.kind === "symbol" && selectedSymbol) {
      commit(
        setSymbol(doc, selection.id, {
          ...selectedSymbol,
          x: round1(selectedSymbol.x + dx),
          y: round1(selectedSymbol.y + dy),
        }),
      );
    }
  }

  function rotate(delta: number) {
    if (selection?.kind !== "symbol" || !selectedSymbol) return;
    const r = (((selectedSymbol.rotation || 0) + delta) % 360 + 360) % 360;
    commit(setSymbol(doc, selection.id, { ...selectedSymbol, rotation: r }));
  }

  /** First room of the floor not linked to any room shape yet. */
  const firstUnlinkedRoom = () => {
    const linked = new Set(doc.shapes.map((s) => s.room_id).filter((id) => id != null));
    return rooms.find((r) => !linked.has(r.id))?.id ?? null;
  };

  function finishDraft() {
    const pts = dedupePoints(draftRef.current);
    if (tool === "room" && pts.length >= 3) {
      const shape: PlanShape = { id: newShapeId(), type: "room", points: pts, room_id: firstUnlinkedRoom() };
      commit({ ...doc, shapes: [...doc.shapes, shape] });
      setSelection({ kind: "shape", id: shape.id });
    } else if (tool === "wall" && pts.length >= 2) {
      const shape: PlanShape = { id: newShapeId(), type: "wall", points: pts };
      commit({ ...doc, shapes: [...doc.shapes, shape] });
      setSelection({ kind: "shape", id: shape.id });
    }
    setDraft([]);
  }

  function cancelCurrent() {
    if (draftRef.current.length || pendingLabel) {
      setDraft([]);
      setPendingLabel(null);
      setMetres("");
      return;
    }
    if (tool !== "select") {
      setTool("select");
      return;
    }
    setSelection(null);
  }

  function setTool(next: EditorTool) {
    setToolState(next);
    setDraft([]);
    setPendingLabel(null);
    setMetres("");
    setCursor(null);
    if (next === "place") setPendingPlace((p) => (p != null && !doc.symbols[p] ? p : (unplaced[0]?.id ?? null)));
  }

  function addLabel() {
    const text = labelText.trim();
    if (!pendingLabel || !text) return;
    const shape: PlanShape = { id: newShapeId(), type: "label", points: [pendingLabel], text };
    commit({ ...doc, shapes: [...doc.shapes, shape] });
    setSelection({ kind: "shape", id: shape.id });
    setPendingLabel(null);
    setLabelText("");
  }

  const measured =
    tool === "scale" && draft.length === 2
      ? Math.hypot(draft[1][0] - draft[0][0], draft[1][1] - draft[0][1])
      : null;
  const metresValue = parseMetres(metres);

  function applyScale() {
    if (!measured || !metresValue) return;
    commit({ ...doc, scale: Math.round((measured / metresValue) * 1000) / 1000 });
    setTool("select");
    toast.success(t("Scale set."));
  }

  // --- Saving ---------------------------------------------------------------

  async function save() {
    if (!dirty || saving) return;
    const target = doc;
    const ids = changedSymbolIds(target, saved);
    type Job = { part: "plan" } | { part: "scale" } | { part: "symbol"; id: number };
    const jobs: Job[] = [];
    const calls: Promise<unknown>[] = [];
    if (target.shapes !== saved.shapes) {
      jobs.push({ part: "plan" });
      calls.push(desksApi.saveFloorPlan(floor.id, { shapes: target.shapes }));
    }
    if ((target.scale ?? null) !== (saved.scale ?? null)) {
      jobs.push({ part: "scale" });
      calls.push(desksApi.updateFloor(floor.id, { scale_px_per_m: target.scale }));
    }
    for (const id of ids) {
      jobs.push({ part: "symbol", id });
      calls.push(desksApi.updatePlace(id, { plan_symbol: target.symbols[id] ?? null }));
    }
    setSaving(true);
    const results = await Promise.allSettled(calls);
    setSaving(false);
    const failed = results.filter((r) => r.status === "rejected") as PromiseRejectedResult[];
    if (!failed.length) {
      setSaved(target);
      toast.success(t("Floor plan saved."));
      return;
    }
    // Keep the failed parts dirty: the new baseline takes only what was saved.
    const next: PlanDoc = { ...saved, symbols: { ...saved.symbols } };
    results.forEach((r, i) => {
      if (r.status !== "fulfilled") return;
      const job = jobs[i];
      if (job.part === "plan") next.shapes = target.shapes;
      else if (job.part === "scale") next.scale = target.scale;
      else next.symbols[job.id] = target.symbols[job.id] ?? null;
    });
    setSaved(next);
    const reason = failed[0].reason instanceof Error ? failed[0].reason.message : "";
    toast.warning(
      `${t("Some changes could not be saved. Please try again.")}${reason ? ` ${reason}` : ""}`,
    );
  }

  // --- Viewport -------------------------------------------------------------

  /** Client point → plan units (through the content group's transform). */
  function toPlan(clientX: number, clientY: number): Point {
    const m = contentRef.current?.getScreenCTM();
    if (!m) return [0, 0];
    const p = new DOMPoint(clientX, clientY).matrixTransform(m.inverse());
    return [p.x, p.y];
  }
  /** Client point → viewBox units (for zooming about the pointer). */
  function toViewBox(clientX: number, clientY: number) {
    const m = svgRef.current?.getScreenCTM();
    if (!m) return { x: W / 2, y: H / 2, a: 1 };
    const p = new DOMPoint(clientX, clientY).matrixTransform(m.inverse());
    return { x: p.x, y: p.y, a: m.a };
  }
  const zoomBy = (factor: number, fx = W / 2, fy = H / 2) =>
    setView((v) => zoomViewAbout(v, factor, fx, fy, W, H, MAX_EDITOR_ZOOM));

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setBox((b) => (Math.abs(b.w - r.width) < 1 && Math.abs(b.h - r.height) < 1 ? b : { w: r.width, h: r.height }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Latest handlers for the long-lived listeners below.
  const live = useRef({ onKey: (_e: KeyboardEvent) => {}, onWheel: (_e: WheelEvent) => {} });
  live.current.onWheel = (e: WheelEvent) => {
    if (e.deltaY > 0 && view.k <= 1) return;
    e.preventDefault();
    const p = toViewBox(e.clientX, e.clientY);
    zoomBy(Math.exp(-e.deltaY * 0.0015), p.x, p.y);
  };
  live.current.onKey = (e: KeyboardEvent) => {
    const target = e.target as Element | null;
    if (isTextTarget(target) || target?.closest?.('[role="dialog"]')) return;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      dispatch({ type: e.shiftKey ? "redo" : "undo" });
    } else if (mod && e.key.toLowerCase() === "y") {
      e.preventDefault();
      dispatch({ type: "redo" });
    } else if (mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      void save();
    } else if (e.key === "Escape") {
      cancelCurrent();
    } else if (e.key === "Enter" && (tool === "room" || tool === "wall") && draftRef.current.length) {
      e.preventDefault();
      finishDraft();
    } else if ((e.key === "Delete" || e.key === "Backspace") && selection) {
      e.preventDefault();
      deleteSelection();
    } else if (e.key.startsWith("Arrow") && selection) {
      e.preventDefault();
      const step = (snapOn ? grid : 1) * (e.shiftKey ? 10 : 1);
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[
        e.key
      ];
      if (d) nudge(d[0], d[1]);
    }
  };
  useEffect(() => {
    const el = svgRef.current;
    const onWheel = (e: WheelEvent) => live.current.onWheel(e);
    const onKey = (e: KeyboardEvent) => live.current.onKey(e);
    el?.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("keydown", onKey);
    return () => {
      el?.removeEventListener("wheel", onWheel);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    if (pendingLabel) labelInput.current?.focus();
  }, [pendingLabel]);
  useEffect(() => {
    if (measured) metresInput.current?.focus();
  }, [measured]);

  // --- Pointer --------------------------------------------------------------

  function capture(e: ReactPointerEvent<SVGSVGElement>) {
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // synthetic pointers cannot be captured
    }
  }

  function onPointerDown(e: ReactPointerEvent<SVGSVGElement>) {
    if (e.button === 1) {
      e.preventDefault();
      gesture.current = { kind: "pan", last: { x: e.clientX, y: e.clientY } };
      capture(e);
      return;
    }
    if (e.button !== 0) return;
    const raw = toPlan(e.clientX, e.clientY);
    const sp = snapPoint(raw, e.altKey);
    switch (tool) {
      case "select": {
        const hit = (e.target as Element).closest<SVGElement>("[data-hit]");
        if (!hit) {
          setSelection(null);
          gesture.current = { kind: "pan", last: { x: e.clientX, y: e.clientY } };
        } else if (hit.dataset.hit === "vertex") {
          gesture.current = {
            kind: "vertex",
            id: hit.dataset.id!,
            index: Number(hit.dataset.index),
            before: doc,
          };
        } else if (hit.dataset.hit === "shape") {
          const id = hit.dataset.id!;
          setSelection({ kind: "shape", id });
          gesture.current = { kind: "shape", id, start: raw, before: doc };
        } else if (hit.dataset.hit === "symbol") {
          const id = Number(hit.dataset.id);
          setSelection({ kind: "symbol", id });
          const origin = doc.symbols[id];
          if (origin) gesture.current = { kind: "symbol", id, start: raw, origin, before: doc };
        }
        capture(e);
        break;
      }
      case "room":
      case "wall":
        setDraft([...draftRef.current, sp]);
        break;
      case "door":
        if (!draftRef.current.length) {
          setDraft([sp]);
        } else {
          const pts = dedupePoints([draftRef.current[0], sp]);
          if (pts.length === 2) {
            const shape: PlanShape = { id: newShapeId(), type: "door", points: pts };
            commit({ ...doc, shapes: [...doc.shapes, shape] });
            setSelection({ kind: "shape", id: shape.id });
          }
          setDraft([]);
        }
        break;
      case "scale": {
        // Measured points stay unsnapped: the grid depends on the scale.
        const p: Point = [round1(raw[0]), round1(raw[1])];
        setDraft(draftRef.current.length === 1 ? [draftRef.current[0], p] : [p]);
        setMetres("");
        break;
      }
      case "label":
        setPendingLabel(sp);
        break;
      case "place":
        if (pendingPlace != null && !doc.symbols[pendingPlace]) {
          commit(setSymbol(doc, pendingPlace, { x: sp[0], y: sp[1], rotation: 0 }));
          setSelection({ kind: "symbol", id: pendingPlace });
          const next = unplaced.find((p) => p.id !== pendingPlace);
          setPendingPlace(next?.id ?? null);
        }
        break;
    }
  }

  function onPointerMove(e: ReactPointerEvent<SVGSVGElement>) {
    const g = gesture.current;
    if (!g) {
      if (tool !== "select") {
        const raw = toPlan(e.clientX, e.clientY);
        setCursor(tool === "scale" ? raw : snapPoint(raw, e.altKey));
      }
      return;
    }
    if (g.kind === "pan") {
      const { a } = toViewBox(e.clientX, e.clientY);
      const dx = (e.clientX - g.last.x) / a;
      const dy = (e.clientY - g.last.y) / a;
      g.last = { x: e.clientX, y: e.clientY };
      setView((v) => clampView({ ...v, x: v.x + dx, y: v.y + dy }, W, H, MAX_EDITOR_ZOOM));
      return;
    }
    const raw = toPlan(e.clientX, e.clientY);
    const free = e.altKey;
    if (g.kind === "shape") {
      const g0 = snapOn && !free ? grid : null;
      const d = snap([raw[0] - g.start[0], raw[1] - g.start[1]], g0);
      dispatch({ type: "live", doc: replaceShape(g.before, g.id, (s) => translateShape(s, d[0], d[1])) });
    } else if (g.kind === "symbol") {
      const p = snapPoint([g.origin.x + raw[0] - g.start[0], g.origin.y + raw[1] - g.start[1]], free);
      dispatch({ type: "live", doc: setSymbol(g.before, g.id, { ...g.origin, x: p[0], y: p[1] }) });
    } else if (g.kind === "vertex") {
      const p = snapPoint(raw, free);
      dispatch({
        type: "live",
        doc: replaceShape(g.before, g.id, (s) => ({
          ...s,
          points: pointsOf(s).map((q, i) => (i === g.index ? p : q)),
        })),
      });
    }
  }

  function onPointerUp() {
    const g = gesture.current;
    gesture.current = null;
    if (g && g.kind !== "pan") dispatch({ type: "endGesture", before: g.before });
  }

  // --- Rendering ------------------------------------------------------------

  const tools: { id: EditorTool; label: string; icon: LucideIcon }[] = [
    { id: "select", label: t("Select and move"), icon: MousePointer2 },
    { id: "room", label: t("Room outline"), icon: Pentagon },
    { id: "wall", label: t("Wall"), icon: BrickWall },
    { id: "door", label: t("Door"), icon: DoorOpen },
    { id: "label", label: t("Text label"), icon: Type },
    { id: "place", label: t("Place symbol"), icon: Armchair },
    { id: "scale", label: t("Set scale"), icon: Ruler },
  ];
  const hints: Record<EditorTool, string> = {
    select: t("Click an element to select it, drag to move it. Drag the background to pan."),
    room: t("Click the corners of the room. Double-click or press Enter to close the outline."),
    wall: t("Click the points of the wall. Double-click or press Enter to finish."),
    door: t("Click the two ends of the door opening."),
    label: t("Click where the text should go."),
    place: t("Choose a place, then click its position on the plan."),
    scale: t("Click the two ends of a known distance, then enter its length in metres."),
  };

  const iconBtn =
    "flex h-10 w-10 items-center justify-center rounded-full border text-slate-800 transition-colors disabled:opacity-40 dark:text-slate-100";
  const quietBtn = `${iconBtn} border-slate-300 bg-white hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700`;
  const pill =
    "inline-flex min-h-[40px] items-center justify-center gap-2 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700";
  const input =
    "min-h-[40px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";
  const panelHeading = "mb-2 text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100";

  const gridPx = grid * pxPerUnit;
  const scaleBar = (() => {
    if (!doc.scale || pxPerUnit <= 0) return null;
    const perM = doc.scale * pxPerUnit;
    const m = [0.5, 1, 2, 5, 10, 20, 50, 100].find((c) => c * perM >= 60) ?? 100;
    return { m, width: m * perM };
  })();

  const linkedRoomName = (s: PlanShape) =>
    s.room_id != null ? (roomById.get(s.room_id)?.name ?? null) : null;

  const handleR = px(6);
  const selectedPoints = selectedShape && selectedShape.type !== "label" ? pointsOf(selectedShape) : [];

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
      <div className="min-w-0 flex-1">
        {/* Toolbar */}
        <div
          role="toolbar"
          aria-label={t("Drawing tools")}
          className="mb-2 flex flex-wrap items-center gap-2"
        >
          <div className="flex flex-wrap gap-1.5">
            {tools.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                aria-pressed={tool === id}
                aria-label={label}
                title={label}
                onClick={() => setTool(id)}
                className={`${iconBtn} ${
                  tool === id
                    ? "border-brand-600 bg-brand-100 text-slate-900 dark:border-brand-400 dark:bg-brand-400 dark:text-slate-900"
                    : "border-slate-300 bg-white hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700"
                }`}
              >
                <Icon aria-hidden className="h-5 w-5" />
              </button>
            ))}
          </div>
          <span aria-hidden className="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-700" />
          <button
            type="button"
            aria-label={t("Undo")}
            title={t("Undo")}
            disabled={!history.past.length}
            onClick={() => dispatch({ type: "undo" })}
            className={quietBtn}
          >
            <Undo2 aria-hidden className="h-5 w-5" />
          </button>
          <button
            type="button"
            aria-label={t("Redo")}
            title={t("Redo")}
            disabled={!history.future.length}
            onClick={() => dispatch({ type: "redo" })}
            className={quietBtn}
          >
            <Redo2 aria-hidden className="h-5 w-5" />
          </button>
          <span aria-hidden className="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-700" />
          <button type="button" aria-label={t("Zoom in")} title={t("Zoom in")} onClick={() => zoomBy(1.5)} className={quietBtn}>
            <ZoomIn aria-hidden className="h-5 w-5" />
          </button>
          <button type="button" aria-label={t("Zoom out")} title={t("Zoom out")} onClick={() => zoomBy(1 / 1.5)} className={quietBtn}>
            <ZoomOut aria-hidden className="h-5 w-5" />
          </button>
          <button
            type="button"
            aria-label={t("Fit to screen")}
            title={t("Fit to screen")}
            onClick={() => setView({ k: 1, x: 0, y: 0 })}
            className={quietBtn}
          >
            <Maximize aria-hidden className="h-5 w-5" />
          </button>
          <div className="ml-auto flex items-center gap-3">
            {dirty && (
              <span className="text-xs font-semibold text-amber-800 dark:text-amber-300">
                {t("Unsaved changes")}
              </span>
            )}
            <button
              type="button"
              onClick={() => void save()}
              disabled={!dirty || saving}
              className="inline-flex min-h-[40px] items-center gap-2 rounded-full bg-brand-400 px-5 text-sm font-bold text-slate-900 hover:bg-brand-500 disabled:opacity-50"
            >
              <Save aria-hidden className="h-4 w-4" />
              {saving ? t("Saving…") : t("Save")}
            </button>
          </div>
        </div>
        <p className="mb-2 text-xs text-slate-600 dark:text-slate-300" aria-live="polite">
          {hints[tool]}
        </p>

        {/* Canvas */}
        <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            role="application"
            aria-label={t("Floor plan editor")}
            aria-describedby={`${uid}-hint`}
            className={`block h-[70vh] w-full touch-none select-none ${
              tool === "select" ? "cursor-default" : "cursor-crosshair"
            }`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onPointerLeave={() => setCursor(null)}
            onDoubleClick={() => {
              if (tool === "room" || tool === "wall") finishDraft();
            }}
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
              <g ref={contentRef}>
                <rect x={0} y={0} width={W} height={H} className="fill-white dark:fill-slate-950" />
                {template && (
                  <image
                    href={template.url}
                    x={0}
                    y={0}
                    width={template.width}
                    height={template.height}
                    opacity={opacity / 100}
                    preserveAspectRatio="none"
                    pointerEvents="none"
                  />
                )}
                {snapOn && gridPx >= 8 && (
                  <rect x={0} y={0} width={W} height={H} fill={`url(#${uid}-grid)`} pointerEvents="none" />
                )}
                <PlanDrawing shapes={doc.shapes} u={u} />

                {/* Linked room names (editor only). */}
                {doc.shapes
                  .filter((s) => s.type === "room" && linkedRoomName(s))
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
                        {linkedRoomName(s)}
                      </text>
                    );
                  })}

                {/* Hit areas of the shapes (selection). */}
                {tool === "select" &&
                  ["room", "wall", "door", "label"].flatMap((type) =>
                    doc.shapes
                      .filter((s) => s.type === type)
                      .map((s) => {
                        const pts = pointsOf(s);
                        const common = {
                          "data-hit": "shape",
                          "data-id": s.id,
                          className: "cursor-move",
                        };
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
                          const w = Math.max(1, (s.text ?? "").length) * u * 0.55 + u;
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
                  .filter((p) => doc.symbols[p.id])
                  .map((p) => {
                    const sym = doc.symbols[p.id]!;
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
                          className="pointer-events-none stroke-brand-600 dark:stroke-brand-300"
                        />
                      </g>
                    );
                  })}

                {/* Selected shape: outline and vertex handles. */}
                {selectedShape && selectedShape.type !== "label" && (
                  <polyline
                    points={[...selectedPoints, ...(selectedShape.type === "room" ? selectedPoints.slice(0, 1) : [])]
                      .map((p) => p.join(","))
                      .join(" ")}
                    fill="none"
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    vectorEffect="non-scaling-stroke"
                    className="pointer-events-none stroke-brand-600 dark:stroke-brand-300"
                  />
                )}
                {selectedShape?.type === "label" && pointsOf(selectedShape)[0] && (
                  <rect
                    x={pointsOf(selectedShape)[0][0] - (Math.max(1, (selectedShape.text ?? "").length) * u * 0.55 + u) / 2}
                    y={pointsOf(selectedShape)[0][1] - u * 0.7}
                    width={Math.max(1, (selectedShape.text ?? "").length) * u * 0.55 + u}
                    height={u * 1.4}
                    rx={u * 0.2}
                    fill="none"
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    vectorEffect="non-scaling-stroke"
                    className="pointer-events-none stroke-brand-600 dark:stroke-brand-300"
                  />
                )}
                {tool === "select" &&
                  selectedShape &&
                  selectedPoints.map(([x, y], i) => (
                    <circle
                      key={`v-${i}`}
                      cx={x}
                      cy={y}
                      r={handleR}
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
                    points={[...draft, ...(cursor ? [cursor] : []), ...(tool === "room" && draft.length > 1 ? [draft[0]] : [])]
                      .map((p) => p.join(","))
                      .join(" ")}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    vectorEffect="non-scaling-stroke"
                    className={`pointer-events-none stroke-brand-600 dark:stroke-brand-300 ${
                      tool === "room" ? "fill-brand-200/30" : "fill-none"
                    }`}
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
                    className="pointer-events-none stroke-brand-600 dark:stroke-brand-300"
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
                  <circle
                    cx={cursor[0]}
                    cy={cursor[1]}
                    r={px(3)}
                    className="pointer-events-none fill-slate-500"
                  />
                )}
              </g>
            </g>
          </svg>
          {scaleBar && (
            <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-white/90 px-2 py-1 text-xs font-semibold text-slate-800 shadow-sm dark:bg-slate-800/90 dark:text-slate-100">
              <div
                aria-hidden
                className="mb-0.5 h-1.5 border-x-2 border-b-2 border-slate-800 dark:border-slate-100"
                style={{ width: `${scaleBar.width}px` }}
              />
              {t("{{m}} m", { m: scaleBar.m.toLocaleString() })}
            </div>
          )}
        </div>
        <p id={`${uid}-hint`} className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {t(
            "Keys: Esc cancels, Delete removes the selection, arrow keys nudge it (Shift: 10×), Ctrl+Z / Ctrl+Y undo and redo. Hold Alt to place without the grid.",
          )}
        </p>
      </div>

      {/* Side panel */}
      <aside className="flex w-full flex-col gap-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700 lg:w-80 lg:shrink-0">
        {/* Current tool */}
        {tool === "label" && pendingLabel && (
          <section>
            <h3 className={panelHeading}>{t("Text label")}</h3>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                addLabel();
              }}
            >
              <label htmlFor={`${uid}-label`} className="sr-only">
                {t("Text")}
              </label>
              <input
                id={`${uid}-label`}
                ref={labelInput}
                value={labelText}
                onChange={(e) => setLabelText(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && cancelCurrent()}
                maxLength={80}
                className={input}
              />
              <button type="submit" disabled={!labelText.trim()} className={pill}>
                {t("Add")}
              </button>
            </form>
          </section>
        )}

        {tool === "place" && (
          <section>
            <h3 className={panelHeading}>{t("Places not on the plan")}</h3>
            {unplaced.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">{t("All places of this floor are on the plan.")}</p>
            ) : (
              <fieldset>
                <legend className="sr-only">{t("Choose a place")}</legend>
                <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto">
                  {unplaced.map((p) => (
                    <li key={p.id}>
                      <label className="flex min-h-[40px] cursor-pointer items-center gap-2 rounded-lg px-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                        <input
                          type="radio"
                          name={`${uid}-place`}
                          checked={pendingPlace === p.id}
                          onChange={() => setPendingPlace(p.id)}
                          className="h-4 w-4 accent-brand-600"
                        />
                        <span className="min-w-0 flex-1 truncate">{p.name}</span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {roomById.get(p.room)?.name} ·{" "}
                          {p.kind === "meeting_room" ? t("Meeting room") : t("Desk")}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            )}
          </section>
        )}

        {tool === "scale" && (
          <section>
            <h3 className={panelHeading}>{t("Set scale")}</h3>
            {measured ? (
              <form
                className="flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  applyScale();
                }}
              >
                <label htmlFor={`${uid}-metres`} className="text-sm text-slate-700 dark:text-slate-200">
                  {t("Real length of the marked distance (m)")}
                </label>
                <input
                  id={`${uid}-metres`}
                  ref={metresInput}
                  inputMode="decimal"
                  value={metres}
                  onChange={(e) => setMetres(e.target.value)}
                  onKeyDown={(e) => e.key === "Escape" && cancelCurrent()}
                  aria-invalid={metres !== "" && !metresValue}
                  className={input}
                />
                {metres !== "" && !metresValue && (
                  <p className="text-xs text-red-700 dark:text-red-300">{t("Enter a length greater than 0.")}</p>
                )}
                <div className="flex gap-2">
                  <button type="submit" disabled={!metresValue} className={pill}>
                    {t("Apply")}
                  </button>
                  <button type="button" onClick={cancelCurrent} className={pill}>
                    {t("Cancel")}
                  </button>
                </div>
              </form>
            ) : (
              <p className="text-sm text-slate-600 dark:text-slate-300">{hints.scale}</p>
            )}
          </section>
        )}

        {/* Selection */}
        {selectedShape && (
          <section>
            <h3 className={panelHeading}>
              {
                {
                  room: t("Room outline"),
                  wall: t("Wall"),
                  door: t("Door"),
                  label: t("Text label"),
                }[selectedShape.type]
              }
            </h3>
            {selectedShape.type === "room" && (
              <div className="mb-3">
                <label htmlFor={`${uid}-room`} className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {t("Linked room")}
                </label>
                <select
                  id={`${uid}-room`}
                  value={selectedShape.room_id ?? ""}
                  onChange={(e) =>
                    commit(
                      replaceShape(doc, selectedShape.id, (s) => ({
                        ...s,
                        room_id: e.target.value ? Number(e.target.value) : null,
                      })),
                    )
                  }
                  className={input}
                >
                  <option value="">{t("No room")}</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {selectedShape.type === "label" && (
              <div className="mb-3">
                <label htmlFor={`${uid}-text`} className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {t("Text")}
                </label>
                <input
                  id={`${uid}-text`}
                  value={selectedShape.text ?? ""}
                  maxLength={80}
                  onFocus={() => (labelBefore.current = doc)}
                  onChange={(e) =>
                    dispatch({
                      type: "live",
                      doc: replaceShape(doc, selectedShape.id, (s) => ({ ...s, text: e.target.value })),
                    })
                  }
                  onBlur={() => {
                    const before = labelBefore.current;
                    labelBefore.current = null;
                    if (!before) return;
                    if (!(selectedShape.text ?? "").trim()) {
                      dispatch({ type: "live", doc: { ...doc, shapes: doc.shapes.filter((s) => s.id !== selectedShape.id) } });
                    }
                    dispatch({ type: "endGesture", before });
                  }}
                  className={input}
                />
              </div>
            )}
            <button type="button" onClick={deleteSelection} className={`${pill} text-red-700 dark:text-red-300`}>
              <Trash2 aria-hidden className="h-4 w-4" />
              {t("Delete")}
            </button>
          </section>
        )}
        {selection?.kind === "symbol" && selectedSymbol && (
          <section>
            <h3 className={panelHeading}>{placeById.get(selection.id)?.name}</h3>
            <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
              {roomById.get(placeById.get(selection.id)?.room ?? -1)?.name} ·{" "}
              {placeById.get(selection.id)?.kind === "meeting_room" ? t("Meeting room") : t("Desk")}
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => rotate(-90)} className={pill}>
                <RotateCcw aria-hidden className="h-4 w-4" />
                {t("Rotate left")}
              </button>
              <button type="button" onClick={() => rotate(90)} className={pill}>
                <RotateCw aria-hidden className="h-4 w-4" />
                {t("Rotate right")}
              </button>
              <button type="button" onClick={deleteSelection} className={`${pill} text-red-700 dark:text-red-300`}>
                <Trash2 aria-hidden className="h-4 w-4" />
                {t("Remove from plan")}
              </button>
            </div>
          </section>
        )}

        {/* Template */}
        <section>
          <h3 className={panelHeading}>{t("Template")}</h3>
          <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
            {t("Upload the existing plan as a template to trace. Only you see it in the editor; users see the redrawn plan.")}
          </p>
          <label className={`${pill} cursor-pointer focus-within:ring-2 focus-within:ring-brand-600`}>
            <Upload aria-hidden className="h-4 w-4" />
            {uploading ? t("Uploading…") : template ? t("Replace template") : t("Upload template")}
            <input
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              className="sr-only"
              disabled={uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) onUploadTemplate(file);
              }}
            />
          </label>
          {template && (
            <div className="mt-3">
              <label htmlFor={`${uid}-opacity`} className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                {t("Template opacity")}: {opacity} %
              </label>
              <input
                id={`${uid}-opacity`}
                type="range"
                min={0}
                max={100}
                step={5}
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
                className="w-full accent-brand-600"
              />
            </div>
          )}
        </section>

        {/* Scale and grid */}
        <section>
          <h3 className={panelHeading}>{t("Scale")}</h3>
          <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">
            {doc.scale
              ? t("1 m = {{n}} plan units", { n: Math.round(doc.scale * 10) / 10 })
              : t("No scale set yet.")}
          </p>
          {tool !== "scale" && (
            <button type="button" onClick={() => setTool("scale")} className={pill}>
              <Ruler aria-hidden className="h-4 w-4" />
              {doc.scale ? t("Change scale") : t("Set scale")}
            </button>
          )}
          <label className="mt-3 flex min-h-[40px] items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              checked={snapOn}
              onChange={(e) => setSnapOn(e.target.checked)}
              className="h-4 w-4 accent-brand-600"
            />
            {doc.scale ? t("Snap to 10 cm grid") : t("Snap to grid")}
          </label>
        </section>
      </aside>
    </div>
  );
}
