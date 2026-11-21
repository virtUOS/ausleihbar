// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useState, type Ref } from "react";
import { useTranslation } from "react-i18next";
import { FlipHorizontal2, FlipVertical2, RotateCcw, RotateCw, Ruler, Trash2, Upload } from "lucide-react";
import type { Place, PlanShape, Room, RoomIcon } from "../types";
import type { EditorTool, PlanTemplate } from "./PlanEditorCanvas";
import { parseMetres, round1 } from "./planEditorState";

export const pillClass =
  "inline-flex min-h-[40px] items-center justify-center gap-2 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700";
const input =
  "min-h-[40px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";
const heading = "mb-2 text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100";
const fieldLabel = "mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300";

interface Props {
  /** Department admins: no template upload and no scale change. */
  symbolsOnly: boolean;
  tool: EditorTool;
  rooms: Room[];
  roomById: Map<number, Room>;
  // Label tool
  pendingLabel: boolean;
  newLabelText: string;
  onNewLabelText: (v: string) => void;
  onAddLabel: () => void;
  labelInputRef: Ref<HTMLInputElement>;
  // Place tool
  unplaced: Place[];
  pendingPlace: number | null;
  onPendingPlace: (id: number) => void;
  // Scale tool
  measured: number | null;
  metres: string;
  metresValid: boolean;
  onMetres: (v: string) => void;
  onApplyScale: () => void;
  metresInputRef: Ref<HTMLInputElement>;
  scaleHint: string;
  onCancel: () => void;
  // Selection
  selectedShape: PlanShape | undefined;
  /** Text shown in the selected label's field (pending edit or stored). */
  labelText: string;
  onLabelText: (v: string) => void;
  onLabelCommit: () => void;
  onLinkRoom: (roomId: number | null) => void;
  onIcon: (icon: RoomIcon | null) => void;
  /** Index of the selected corner of the selected room (null: none). */
  selectedCorner: number | null;
  onRemoveCorner: () => void;
  /** New width of the selected door/window (plan units). */
  onOpeningWidth: (width: number) => void;
  onFlip: (flag: "flip_hinge" | "flip_swing") => void;
  selectedPlace: Place | undefined;
  onRotate: (delta: number) => void;
  onDelete: () => void;
  // Template, scale, grid
  template: PlanTemplate | null;
  uploading: boolean;
  onUpload: (file: File) => void;
  opacity: number;
  onOpacity: (v: number) => void;
  scale: number | null;
  onStartScale: () => void;
  snapOn: boolean;
  onSnap: (v: boolean) => void;
}

/** Side panel of the plan editor: options of the current tool, properties of
 *  the selection, template, scale and grid. */
export function PlanEditorPanel(p: Props) {
  const { t } = useTranslation();
  const uid = useId();
  const kindLabel = (place: Place) => (place.kind === "meeting_room" ? t("Meeting room") : t("Desk"));
  const shapeTitle: Record<PlanShape["type"], string> = {
    room: t("Room outline"),
    wall: t("Wall"),
    door: t("Door"),
    window: t("Window"),
    label: t("Text label"),
  };
  const escCancels = (e: { key: string }) => e.key === "Escape" && p.onCancel();
  const icons: { value: RoomIcon; label: string }[] = [
    { value: "stairs", label: t("Stairs") },
    { value: "wc_men", label: t("Men's toilet") },
    { value: "wc_women", label: t("Women's toilet") },
    { value: "wc_accessible", label: t("Accessible toilet") },
  ];
  const shape = p.selectedShape;

  return (
    <aside className="flex w-full flex-col gap-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700 lg:w-80 lg:shrink-0">
      {p.tool === "label" && p.pendingLabel && (
        <section>
          <h3 className={heading}>{t("Text label")}</h3>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              p.onAddLabel();
            }}
          >
            <label htmlFor={`${uid}-label`} className="sr-only">
              {t("Text")}
            </label>
            <input
              id={`${uid}-label`}
              ref={p.labelInputRef}
              value={p.newLabelText}
              onChange={(e) => p.onNewLabelText(e.target.value)}
              onKeyDown={escCancels}
              maxLength={80}
              className={input}
            />
            <button type="submit" disabled={!p.newLabelText.trim()} className={pillClass}>
              {t("Add")}
            </button>
          </form>
        </section>
      )}

      {p.tool === "place" && (
        <section>
          <h3 className={heading}>{t("Places not on the plan")}</h3>
          {p.unplaced.length === 0 ? (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {t("All places of this floor are on the plan.")}
            </p>
          ) : (
            <fieldset>
              <legend className="sr-only">{t("Choose a place")}</legend>
              <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto">
                {p.unplaced.map((place) => (
                  <li key={place.id}>
                    <label className="flex min-h-[40px] cursor-pointer items-center gap-2 rounded-lg px-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                      <input
                        type="radio"
                        name={`${uid}-place`}
                        checked={p.pendingPlace === place.id}
                        onChange={() => p.onPendingPlace(place.id)}
                        className="h-4 w-4 accent-brand-600"
                      />
                      <span className="min-w-0 flex-1 truncate">{place.name}</span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {p.roomById.get(place.room)?.name} · {kindLabel(place)}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}
        </section>
      )}

      {p.tool === "scale" && (
        <section>
          <h3 className={heading}>{t("Set scale")}</h3>
          {p.measured ? (
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                p.onApplyScale();
              }}
            >
              <label htmlFor={`${uid}-metres`} className="text-sm text-slate-700 dark:text-slate-200">
                {t("Real length of the marked distance (m)")}
              </label>
              <input
                id={`${uid}-metres`}
                ref={p.metresInputRef}
                inputMode="decimal"
                value={p.metres}
                onChange={(e) => p.onMetres(e.target.value)}
                onKeyDown={escCancels}
                aria-invalid={p.metres !== "" && !p.metresValid}
                className={input}
              />
              {p.metres !== "" && !p.metresValid && (
                <p className="text-xs text-red-700 dark:text-red-300">{t("Enter a length greater than 0.")}</p>
              )}
              <div className="flex gap-2">
                <button type="submit" disabled={!p.metresValid} className={pillClass}>
                  {t("Apply")}
                </button>
                <button type="button" onClick={p.onCancel} className={pillClass}>
                  {t("Cancel")}
                </button>
              </div>
            </form>
          ) : (
            <p className="text-sm text-slate-600 dark:text-slate-300">{p.scaleHint}</p>
          )}
        </section>
      )}

      {p.selectedShape && (
        <section>
          <h3 className={heading}>{shapeTitle[p.selectedShape.type]}</h3>
          {p.selectedShape.type === "room" && (
            <div className="mb-3">
              <label htmlFor={`${uid}-room`} className={fieldLabel}>
                {t("Linked room")}
              </label>
              <select
                id={`${uid}-room`}
                value={p.selectedShape.room_id ?? ""}
                onChange={(e) => p.onLinkRoom(e.target.value ? Number(e.target.value) : null)}
                className={input}
              >
                <option value="">{t("No room")}</option>
                {p.rooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
              <label htmlFor={`${uid}-icon`} className={`${fieldLabel} mt-3`}>
                {t("Symbol")}
              </label>
              <select
                id={`${uid}-icon`}
                value={p.selectedShape.icon ?? ""}
                onChange={(e) => p.onIcon((e.target.value || null) as RoomIcon | null)}
                className={input}
              >
                <option value="">{t("No symbol")}</option>
                {icons.map((i) => (
                  <option key={i.value} value={i.value}>
                    {i.label}
                  </option>
                ))}
              </select>
              {p.selectedCorner !== null && (
                <div className="mt-3">
                  <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
                    {t("Corner {{n}} selected. Drag it to move it; Alt detaches it from docked rooms.", {
                      n: p.selectedCorner + 1,
                    })}
                  </p>
                  <button
                    type="button"
                    onClick={p.onRemoveCorner}
                    disabled={(p.selectedShape.points?.length ?? 0) <= 3}
                    className={pillClass}
                  >
                    <Trash2 aria-hidden className="h-4 w-4" />
                    {t("Remove corner")}
                  </button>
                </div>
              )}
            </div>
          )}
          {shape?.wall && (
            <div className="mb-3 flex flex-col gap-3">
              <WidthField key={shape.id} shape={shape} scale={p.scale} onCommit={p.onOpeningWidth} />
              {shape.type === "door" && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    aria-pressed={!!shape.flip_hinge}
                    onClick={() => p.onFlip("flip_hinge")}
                    className={pillClass}
                  >
                    <FlipHorizontal2 aria-hidden className="h-4 w-4" />
                    {t("Mirror hinge side")}
                  </button>
                  <button
                    type="button"
                    aria-pressed={!!shape.flip_swing}
                    onClick={() => p.onFlip("flip_swing")}
                    className={pillClass}
                  >
                    <FlipVertical2 aria-hidden className="h-4 w-4" />
                    {t("Mirror opening direction")}
                  </button>
                </div>
              )}
            </div>
          )}
          {p.selectedShape.type === "label" && (
            <div className="mb-3">
              <label htmlFor={`${uid}-text`} className={fieldLabel}>
                {t("Text")}
              </label>
              <input
                id={`${uid}-text`}
                value={p.labelText}
                maxLength={80}
                onChange={(e) => p.onLabelText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    p.onLabelCommit();
                  }
                }}
                onBlur={p.onLabelCommit}
                className={input}
              />
            </div>
          )}
          <button type="button" onClick={p.onDelete} className={`${pillClass} text-red-700 dark:text-red-300`}>
            <Trash2 aria-hidden className="h-4 w-4" />
            {t("Delete")}
          </button>
        </section>
      )}
      {p.selectedPlace && (
        <section>
          <h3 className={heading}>{p.selectedPlace.name}</h3>
          <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
            {p.roomById.get(p.selectedPlace.room)?.name} · {kindLabel(p.selectedPlace)}
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => p.onRotate(-90)} className={pillClass}>
              <RotateCcw aria-hidden className="h-4 w-4" />
              {t("Rotate left")}
            </button>
            <button type="button" onClick={() => p.onRotate(90)} className={pillClass}>
              <RotateCw aria-hidden className="h-4 w-4" />
              {t("Rotate right")}
            </button>
            <button type="button" onClick={p.onDelete} className={`${pillClass} text-red-700 dark:text-red-300`}>
              <Trash2 aria-hidden className="h-4 w-4" />
              {t("Remove from plan")}
            </button>
          </div>
        </section>
      )}

      {/* Department admins only see an uploaded template (and its opacity). */}
      {(!p.symbolsOnly || p.template) && (
        <section>
          <h3 className={heading}>{t("Template")}</h3>
          {!p.symbolsOnly && (
            <>
              <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
                {t(
                  "Upload the existing plan as a template to trace. Only you see it in the editor; users see the redrawn plan.",
                )}
                {p.template &&
                  ` ${t("Replace it only with an image of the same size: the drawing keeps its coordinates and would no longer match.")}`}
              </p>
              <label className={`${pillClass} cursor-pointer focus-within:ring-2 focus-within:ring-brand-600`}>
                <Upload aria-hidden className="h-4 w-4" />
                {p.uploading ? t("Uploading…") : p.template ? t("Replace template") : t("Upload template")}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="sr-only"
                  disabled={p.uploading}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) p.onUpload(file);
                  }}
                />
              </label>
            </>
          )}
          {p.template && (
            <div className={p.symbolsOnly ? "" : "mt-3"}>
              <label htmlFor={`${uid}-opacity`} className={fieldLabel}>
                {t("Template opacity")}: {p.opacity} %
              </label>
              <input
                id={`${uid}-opacity`}
                type="range"
                min={0}
                max={100}
                step={5}
                value={p.opacity}
                onChange={(e) => p.onOpacity(Number(e.target.value))}
                className="w-full accent-brand-600"
              />
            </div>
          )}
        </section>
      )}

      <section>
        <h3 className={heading}>{t("Scale")}</h3>
        <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">
          {p.scale
            ? t("1 m = {{n}} plan units", { n: Math.round(p.scale * 10) / 10 })
            : t("No scale set yet.")}
        </p>
        {p.tool !== "scale" && !p.symbolsOnly && (
          <button type="button" onClick={p.onStartScale} className={pillClass}>
            <Ruler aria-hidden className="h-4 w-4" />
            {p.scale ? t("Change scale") : t("Set scale")}
          </button>
        )}
        <label className="mt-3 flex min-h-[40px] items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <input
            type="checkbox"
            checked={p.snapOn}
            onChange={(e) => p.onSnap(e.target.checked)}
            className="h-4 w-4 accent-brand-600"
          />
          {p.scale ? t("Snap to 10 cm grid") : t("Snap to grid")}
        </label>
      </section>
    </aside>
  );
}

/** Width of the selected door/window: metres with a scale, else plan units.
 *  Edited as text and applied on Enter or leaving the field (one undo step). */
function WidthField({
  shape,
  scale,
  onCommit,
}: {
  shape: PlanShape;
  scale: number | null;
  onCommit: (width: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const uid = useId();
  const width = shape.width ?? 0;
  const shown = scale ? Math.round((width / scale) * 100) / 100 : round1(width);
  const format = (n: number) => n.toLocaleString(i18n.language, { maximumFractionDigits: 2, useGrouping: false });
  const [text, setText] = useState(format(shown));
  // Undo/redo or another edit changed the width: show the stored value.
  useEffect(() => setText(format(shown)), [shown]); // eslint-disable-line react-hooks/exhaustive-deps
  const apply = () => {
    // Untouched field: the rounded display must not rewrite the width.
    if (text === format(shown)) return;
    const v = parseMetres(text);
    if (!v) return setText(format(shown));
    const units = round1(scale ? v * scale : v);
    if (units > 0 && units !== width) onCommit(units);
    else setText(format(shown));
  };
  return (
    <div>
      <label htmlFor={`${uid}-width`} className={fieldLabel}>
        {scale ? t("Width (m)") : t("Width (plan units)")}
      </label>
      <input
        id={`${uid}-width`}
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            apply();
          } else if (e.key === "Escape") setText(format(shown));
        }}
        onBlur={apply}
        className={input}
      />
    </div>
  );
}
