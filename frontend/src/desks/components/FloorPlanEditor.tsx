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
  Ruler,
  Save,
  Type,
  Undo2,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { useToast } from "../../components/Toast";
import { useUnsavedChangesGuard } from "../../components/useUnsavedChangesGuard";
import { desksApi } from "../api";
import type { Floor, Place, PlanShape, PlanSymbol, Room } from "../types";
import { clampView, symbolUnit, zoomViewAbout, type View } from "./planGeometry";
import {
  changedSymbolIds,
  clampDelta,
  clampPoint,
  dedupePoints,
  gridSize,
  historyReducer,
  newShapeId,
  parseMetres,
  round1,
  sameShapes,
  snap,
  translateShape,
  type PlanDoc,
  type Point,
} from "./planEditorState";
import {
  PlanEditorCanvas,
  type EditorTool,
  type PlanTemplate,
  type Selection,
} from "./PlanEditorCanvas";
import { PlanEditorPanel } from "./PlanEditorPanel";

export type { EditorTool, PlanTemplate } from "./PlanEditorCanvas";

/** A running pointer gesture on the canvas. */
type Gesture =
  | { kind: "pan"; last: { x: number; y: number } }
  | { kind: "shape"; id: string; start: Point; origin: Point[]; before: PlanDoc }
  | { kind: "symbol"; id: number; start: Point; origin: PlanSymbol; before: PlanDoc }
  | { kind: "vertex"; id: string; index: number; origin: Point; before: PlanDoc };

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
const samePoint = (a: Point, b: Point) => a[0] === b[0] && a[1] === b[1];

const isTextTarget = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  (el.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName));

/** Floor-plan editor of department admins (spec "Places, rooms, location,
 *  equipment"): the uploaded plan is a scale template in the background; the
 *  admin redraws rooms, walls, doors and labels on top and places the floor's
 *  desks and meeting rooms as symbols. Users only ever see the redrawn plan.
 *  Plan units are the template's pixels (default canvas 1000 × 700 without
 *  one). "Speichern" writes the plan, the scale and every changed symbol.
 *
 *  This shell owns the document, history, tools and pointer/keyboard logic;
 *  `PlanEditorCanvas` draws, `PlanEditorPanel` shows options and properties. */
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
  const [history, dispatch] = useReducer(historyReducer, { past: [], present: initial, future: [] });
  const doc = history.present;
  const docRef = useRef(doc);
  docRef.current = doc;
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
  const [newLabelText, setNewLabelText] = useState("");
  /** Uncommitted text edit of a selected label (one undo step on commit). */
  const [labelEdit, setLabelEditState] = useState<{ id: string; text: string } | null>(null);
  const labelEditRef = useRef<{ id: string; text: string } | null>(null);
  const setLabelEdit = (v: { id: string; text: string } | null) => {
    labelEditRef.current = v;
    setLabelEditState(v);
  };
  const [pendingPlace, setPendingPlace] = useState<number | null>(null);
  const [metres, setMetres] = useState("");
  const [opacity, setOpacity] = useState(50);
  const [snapOn, setSnapOn] = useState(true);
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const [box, setBox] = useState({ w: 0, h: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  const contentRef = useRef<SVGGElement>(null);
  const gesture = useRef<Gesture | null>(null);
  const labelInput = useRef<HTMLInputElement>(null);
  const metresInput = useRef<HTMLInputElement>(null);

  // --- Derived ---------------------------------------------------------------

  /** Canvas in plan units: the template's size (or the default), grown to
   *  cover what was drawn before. Fixed while editing so nothing jumps. */
  const { W, H } = useMemo(() => {
    let w = template?.width ?? DEFAULT_CANVAS.w;
    let h = template?.height ?? DEFAULT_CANVAS.h;
    for (const s of initial.shapes)
      for (const [x, y] of pointsOf(s)) (w = Math.max(w, x + 20), h = Math.max(h, y + 20));
    for (const s of Object.values(initial.symbols))
      if (s) (w = Math.max(w, s.x + 40), h = Math.max(h, s.y + 40));
    return { W: Math.ceil(w), H: Math.ceil(h) };
  }, [template, initial]);

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

  // Value comparison: a gesture that changed nothing never reads as dirty.
  const shapesDirty = useMemo(() => !sameShapes(doc.shapes, saved.shapes), [doc.shapes, saved.shapes]);
  const symbolsDirty = changedSymbolIds(doc, saved);
  const scaleDirty = (doc.scale ?? null) !== (saved.scale ?? null);
  const dirty = shapesDirty || scaleDirty || symbolsDirty.length > 0 || labelEdit !== null;
  useUnsavedChangesGuard(dirty);

  const selectedShape =
    selection?.kind === "shape" ? doc.shapes.find((s) => s.id === selection.id) : undefined;
  const selectedSymbol = selection?.kind === "symbol" ? doc.symbols[selection.id] : undefined;

  /** Shapes as drawn: with the label text being typed. */
  const shownShapes = useMemo(
    () =>
      labelEdit
        ? doc.shapes.map((s) => (s.id === labelEdit.id ? { ...s, text: labelEdit.text } : s))
        : doc.shapes,
    [doc.shapes, labelEdit],
  );

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

  /** Snapped (unless `free`) and kept on the canvas. */
  const snapPoint = (p: Point, free = false): Point =>
    clampPoint(snap(p, snapOn && !free ? grid : null), W, H);

  /** Commits a pending label text edit (empty text removes the label) and
   *  returns the resulting document, so a caller in the same event can build
   *  on it. */
  function commitLabel(): PlanDoc {
    const edit = labelEditRef.current;
    const base = docRef.current;
    if (!edit) return base;
    setLabelEdit(null);
    const shape = base.shapes.find((s) => s.id === edit.id);
    if (!shape || edit.text === (shape.text ?? "")) return base;
    const next = edit.text.trim()
      ? replaceShape(base, edit.id, (s) => ({ ...s, text: edit.text }))
      : { ...base, shapes: base.shapes.filter((s) => s.id !== edit.id) };
    commit(next);
    docRef.current = next;
    return next;
  }

  // A pending label edit is committed as soon as another object is selected.
  useEffect(() => {
    const edit = labelEditRef.current;
    if (edit && !(selection?.kind === "shape" && selection.id === edit.id)) commitLabel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection]);

  function deleteSelection() {
    if (selection?.kind === "shape") {
      setLabelEdit(null);
      commit({ ...doc, shapes: doc.shapes.filter((s) => s.id !== selection.id) });
    } else if (selection?.kind === "symbol") {
      commit(setSymbol(doc, selection.id, null));
    }
    setSelection(null);
  }

  function nudge(dx: number, dy: number) {
    if (selection?.kind === "shape" && selectedShape) {
      const [cx, cy] = clampDelta(pointsOf(selectedShape), dx, dy, W, H);
      if (cx || cy) commit(replaceShape(doc, selection.id, (s) => translateShape(s, cx, cy)));
    } else if (selection?.kind === "symbol" && selectedSymbol) {
      const [x, y] = clampPoint(
        [round1(selectedSymbol.x + dx), round1(selectedSymbol.y + dy)],
        W,
        H,
      );
      if (x !== selectedSymbol.x || y !== selectedSymbol.y)
        commit(setSymbol(doc, selection.id, { ...selectedSymbol, x, y }));
    }
  }

  function rotate(delta: number) {
    if (selection?.kind !== "symbol" || !selectedSymbol) return;
    const r = ((((selectedSymbol.rotation || 0) + delta) % 360) + 360) % 360;
    commit(setSymbol(doc, selection.id, { ...selectedSymbol, rotation: r }));
  }

  /** First room of the floor not linked to any room shape yet. */
  const firstUnlinkedRoom = () => {
    const linked = new Set(doc.shapes.map((s) => s.room_id).filter((id) => id != null));
    return rooms.find((r) => !linked.has(r.id))?.id ?? null;
  };

  function finishDraft() {
    const pts = dedupePoints(draftRef.current);
    // A double-click's extra point may jitter by a pixel or two; clicking the
    // first corner again to close a room repeats it — drop both.
    const near = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]) < px(5);
    while (pts.length > 1 && near(pts[pts.length - 1], pts[pts.length - 2])) pts.pop();
    if (tool === "room" && pts.length > 3 && near(pts[pts.length - 1], pts[0])) pts.pop();
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
    if (next === "place")
      setPendingPlace((p) => (p != null && !doc.symbols[p] ? p : (unplaced[0]?.id ?? null)));
  }

  function addLabel() {
    const text = newLabelText.trim();
    if (!pendingLabel || !text) return;
    const shape: PlanShape = { id: newShapeId(), type: "label", points: [pendingLabel], text };
    commit({ ...doc, shapes: [...doc.shapes, shape] });
    setSelection({ kind: "shape", id: shape.id });
    setPendingLabel(null);
    setNewLabelText("");
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

  async function save(target: PlanDoc = doc) {
    if (saving) return;
    const ids = changedSymbolIds(target, saved);
    type Job = { part: "plan" } | { part: "scale" } | { part: "symbol"; id: number };
    const jobs: Job[] = [];
    const calls: Promise<unknown>[] = [];
    if (!sameShapes(target.shapes, saved.shapes)) {
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
    if (!jobs.length) return;
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
      setBox((b) =>
        Math.abs(b.w - r.width) < 1 && Math.abs(b.h - r.height) < 1 ? b : { w: r.width, h: r.height },
      );
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
    const mod = e.ctrlKey || e.metaKey;
    if (target?.closest?.('[role="dialog"]')) return;
    // Save works everywhere, also while typing a label.
    if (mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      void save(commitLabel());
      return;
    }
    if (isTextTarget(target)) return;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      dispatch({ type: e.shiftKey ? "redo" : "undo" });
    } else if (mod && e.key.toLowerCase() === "y") {
      e.preventDefault();
      dispatch({ type: "redo" });
    } else if (e.key === "Escape") {
      cancelCurrent();
    } else if (e.key === "Enter") {
      // Only from the canvas (or nothing focused): Enter on a button presses it.
      const onCanvas = target === document.body || !!(target && svgRef.current?.contains(target));
      if (onCanvas && (tool === "room" || tool === "wall") && draftRef.current.length) {
        e.preventDefault();
        finishDraft();
      }
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
    // Keyboard focus follows the pointer onto the canvas (Enter, Delete …).
    if (document.activeElement !== e.currentTarget) e.currentTarget.focus({ preventScroll: true });
    const base = commitLabel();
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
          const id = hit.dataset.id!;
          const index = Number(hit.dataset.index);
          const shape = base.shapes.find((s) => s.id === id);
          const origin = shape ? pointsOf(shape)[index] : undefined;
          if (origin) gesture.current = { kind: "vertex", id, index, origin, before: base };
        } else if (hit.dataset.hit === "shape") {
          const id = hit.dataset.id!;
          setSelection({ kind: "shape", id });
          const shape = base.shapes.find((s) => s.id === id);
          if (shape)
            gesture.current = { kind: "shape", id, start: raw, origin: pointsOf(shape), before: base };
        } else if (hit.dataset.hit === "symbol") {
          const id = Number(hit.dataset.id);
          setSelection({ kind: "symbol", id });
          const origin = base.symbols[id];
          if (origin) gesture.current = { kind: "symbol", id, start: raw, origin, before: base };
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
            commit({ ...base, shapes: [...base.shapes, shape] });
            setSelection({ kind: "shape", id: shape.id });
          }
          setDraft([]);
        }
        break;
      case "scale": {
        // Measured points stay unsnapped: the grid depends on the scale.
        const p = clampPoint([round1(raw[0]), round1(raw[1])], W, H);
        setDraft(draftRef.current.length === 1 ? [draftRef.current[0], p] : [p]);
        setMetres("");
        break;
      }
      case "label":
        setPendingLabel(sp);
        break;
      case "place":
        if (pendingPlace != null && !base.symbols[pendingPlace]) {
          commit(setSymbol(base, pendingPlace, { x: sp[0], y: sp[1], rotation: 0 }));
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
        setCursor(tool === "scale" ? clampPoint(raw, W, H) : snapPoint(raw, e.altKey));
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
    // No movement (jitter of a click) shows the untouched document.
    if (g.kind === "shape") {
      const s = snap([raw[0] - g.start[0], raw[1] - g.start[1]], snapOn && !free ? grid : null);
      const [dx, dy] = clampDelta(g.origin, s[0], s[1], W, H);
      dispatch({
        type: "live",
        doc:
          dx === 0 && dy === 0
            ? g.before
            : replaceShape(g.before, g.id, (sh) => translateShape(sh, dx, dy)),
      });
    } else if (g.kind === "symbol") {
      const p = snapPoint([g.origin.x + raw[0] - g.start[0], g.origin.y + raw[1] - g.start[1]], free);
      dispatch({
        type: "live",
        doc:
          p[0] === g.origin.x && p[1] === g.origin.y
            ? g.before
            : setSymbol(g.before, g.id, { ...g.origin, x: p[0], y: p[1] }),
      });
    } else if (g.kind === "vertex") {
      const p = snapPoint(raw, free);
      dispatch({
        type: "live",
        doc: samePoint(p, g.origin)
          ? g.before
          : replaceShape(g.before, g.id, (sh) => ({
              ...sh,
              points: pointsOf(sh).map((q, i) => (i === g.index ? p : q)),
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

  const scaleBar = (() => {
    if (!doc.scale || pxPerUnit <= 0) return null;
    const perM = doc.scale * pxPerUnit;
    const m = [0.5, 1, 2, 5, 10, 20, 50, 100].find((c) => c * perM >= 60) ?? 100;
    return { m, width: m * perM };
  })();

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
      <div className="min-w-0 flex-1">
        <div role="toolbar" aria-label={t("Drawing tools")} className="mb-2 flex flex-wrap items-center gap-2">
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
          <button
            type="button"
            aria-label={t("Zoom out")}
            title={t("Zoom out")}
            onClick={() => zoomBy(1 / 1.5)}
            className={quietBtn}
          >
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
              onClick={() => void save(commitLabel())}
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

        <PlanEditorCanvas
          svgRef={svgRef}
          contentRef={contentRef}
          uid={uid}
          describedBy={`${uid}-hint`}
          W={W}
          H={H}
          view={view}
          u={u}
          grid={grid}
          showGrid={snapOn && grid * pxPerUnit >= 8}
          pxPerUnit={pxPerUnit}
          template={template}
          opacity={opacity}
          shapes={shownShapes}
          places={places}
          symbols={doc.symbols}
          roomName={(id) => (id != null ? (roomById.get(id)?.name ?? null) : null)}
          tool={tool}
          selection={selection}
          draft={draft}
          cursor={cursor}
          pendingLabel={pendingLabel}
          scaleBar={scaleBar}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => setCursor(null)}
          onDoubleClick={() => {
            if (tool === "room" || tool === "wall") finishDraft();
          }}
        />
        <p id={`${uid}-hint`} className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {t(
            "Keys: Esc cancels, Delete removes the selection, arrow keys nudge it (Shift: 10×), Ctrl+Z / Ctrl+Y undo and redo. Hold Alt to place without the grid.",
          )}
        </p>
      </div>

      <PlanEditorPanel
        tool={tool}
        rooms={rooms}
        roomById={roomById}
        pendingLabel={!!pendingLabel}
        newLabelText={newLabelText}
        onNewLabelText={setNewLabelText}
        onAddLabel={addLabel}
        labelInputRef={labelInput}
        unplaced={unplaced}
        pendingPlace={pendingPlace}
        onPendingPlace={setPendingPlace}
        measured={measured}
        metres={metres}
        metresValid={!!metresValue}
        onMetres={setMetres}
        onApplyScale={applyScale}
        metresInputRef={metresInput}
        scaleHint={hints.scale}
        onCancel={cancelCurrent}
        selectedShape={selectedShape}
        labelText={
          selectedShape && labelEdit?.id === selectedShape.id ? labelEdit.text : (selectedShape?.text ?? "")
        }
        onLabelText={(text) => selectedShape && setLabelEdit({ id: selectedShape.id, text })}
        onLabelCommit={() => void commitLabel()}
        onLinkRoom={(roomId) =>
          selectedShape && commit(replaceShape(doc, selectedShape.id, (s) => ({ ...s, room_id: roomId })))
        }
        selectedPlace={selection?.kind === "symbol" && selectedSymbol ? placeById.get(selection.id) : undefined}
        onRotate={rotate}
        onDelete={deleteSelection}
        template={template}
        uploading={uploading}
        onUpload={onUploadTemplate}
        opacity={opacity}
        onOpacity={setOpacity}
        scale={doc.scale}
        onStartScale={() => setTool("scale")}
        snapOn={snapOn}
        onSnap={setSnapOn}
      />
    </div>
  );
}
