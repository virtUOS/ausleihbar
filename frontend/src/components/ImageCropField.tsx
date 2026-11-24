// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";
import "react-easy-crop/react-easy-crop.css";
import { useModal } from "./useModal";

/** What the parent form should do with the image when it saves. */
export type ImageAction =
  | { kind: "set"; blob: Blob }
  | { kind: "clear" }
  | null;

/** Long side, in pixels, an SVG is rasterized to before cropping. */
const SVG_RASTER_SIZE = 2048;

/** Absolute length of an SVG width/height attribute in px (unitless or px), else null. */
function svgLength(value: string | null): number | null {
  const match = value?.trim().match(/^(\d+(?:\.\d+)?)(px)?$/);
  const n = match ? Number(match[1]) : NaN;
  return n > 0 ? n : null;
}

/** Rasterize an SVG file to a large PNG object URL. Browsers give SVGs
 *  without a fixed pixel size a tiny default (Chrome 300×150) or none at all
 *  (Firefox), so the crop came out blurry or empty. The size is taken from
 *  width/height, else the viewBox; the root gets explicit dimensions so every
 *  browser draws it at full resolution. */
async function rasterizeSvg(file: File): Promise<string> {
  const doc = new DOMParser().parseFromString(await file.text(), "image/svg+xml");
  const root = doc.documentElement;
  if (root.nodeName !== "svg") throw new Error("Invalid SVG.");
  const box = (root.getAttribute("viewBox") ?? "").trim().split(/[\s,]+/).map(Number);
  const hasBox = box.length === 4 && box[2] > 0 && box[3] > 0;
  const attrW = svgLength(root.getAttribute("width"));
  const attrH = svgLength(root.getAttribute("height"));
  const ratio = attrW && attrH ? attrW / attrH : hasBox ? box[2] / box[3] : 1;
  if (!hasBox && attrW && attrH) root.setAttribute("viewBox", `0 0 ${attrW} ${attrH}`);
  const width = Math.round(ratio >= 1 ? SVG_RASTER_SIZE : SVG_RASTER_SIZE * ratio);
  const height = Math.round(ratio >= 1 ? SVG_RASTER_SIZE / ratio : SVG_RASTER_SIZE);
  root.setAttribute("width", String(width));
  root.setAttribute("height", String(height));
  const svgUrl = URL.createObjectURL(
    new Blob([new XMLSerializer().serializeToString(doc)], { type: "image/svg+xml" }),
  );
  try {
    const image = await loadImage(svgUrl);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas not supported.");
    ctx.drawImage(image, 0, 0, width, height);
    const png = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not encode image."))), "image/png"),
    );
    return URL.createObjectURL(png);
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/** Draw the selected crop area onto a canvas and export it as a JPEG blob. */
async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const image = await loadImage(src);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(area.width);
  canvas.height = Math.round(area.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported.");
  // JPEG has no alpha: transparent areas (logos, SVGs) become white, not black.
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(
    image,
    area.x,
    area.y,
    area.width,
    area.height,
    0,
    0,
    area.width,
    area.height,
  );
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Could not encode image."))),
      "image/jpeg",
      0.9,
    );
  });
}

interface Props {
  /** Current stored image URL (null/empty when none). */
  currentUrl?: string | null;
  /** Crop aspect ratio (width / height). Defaults to 1:1 (square). */
  aspect?: number;
  /** Fallback symbol shown when there is no image. */
  fallback?: React.ReactNode;
  /** Reports the pending change to the parent form. */
  onChange: (action: ImageAction) => void;
}

export function ImageCropField({
  currentUrl,
  aspect = 1,
  fallback = "📷",
  onChange,
}: Props) {
  const { t } = useTranslation();
  const fileInput = useRef<HTMLInputElement>(null);
  const [editSrc, setEditSrc] = useState<string | null>(null); // object URL while cropping
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);
  const [preview, setPreview] = useState<string | null>(null); // cropped result preview
  const [removed, setRemoved] = useState(false);

  // Revoke object URLs when they change / on unmount to avoid leaks.
  useEffect(() => () => {
    if (editSrc) URL.revokeObjectURL(editSrc);
  }, [editSrc]);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  useModal(editSrc !== null, panelRef, () => closeEditor());

  const onCropComplete = useCallback((_: Area, pixels: Area) => setArea(pixels), []);

  const [pickError, setPickError] = useState<string | null>(null);

  async function pickFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    setPickError(null);
    let src: string;
    try {
      src =
        file.type === "image/svg+xml" || /\.svg$/i.test(file.name)
          ? await rasterizeSvg(file)
          : URL.createObjectURL(file);
    } catch {
      setPickError(t("The image could not be read."));
      return;
    }
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setEditSrc(src);
  }

  async function applyCrop() {
    if (!editSrc || !area) return;
    const blob = await cropToBlob(editSrc, area);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(blob));
    setRemoved(false);
    onChange({ kind: "set", blob });
    closeEditor();
  }

  function closeEditor() {
    if (editSrc) URL.revokeObjectURL(editSrc);
    setEditSrc(null);
    setArea(null);
  }

  function remove() {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setRemoved(true);
    onChange({ kind: "clear" });
  }

  const shownUrl = preview ?? (removed ? null : currentUrl || null);

  return (
    <div>
      <div
        className="flex items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 text-3xl dark:border-slate-800 dark:bg-slate-800/50"
        style={{ aspectRatio: String(aspect), maxWidth: 180 }}
      >
        {shownUrl ? (
          <img src={shownUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <span aria-hidden>{fallback}</span>
        )}
      </div>

      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {shownUrl ? t("Change image") : t("Upload image")}
        </button>
        {shownUrl && (
          <button
            type="button"
            onClick={remove}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-slate-600 dark:text-red-300 dark:hover:bg-red-950/40"
          >
            {t("Remove")}
          </button>
        )}
      </div>
      {pickError && (
        <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-300">
          {pickError}
        </p>
      )}
      <input
        ref={fileInput}
        type="file"
        accept="image/*"
        onChange={pickFile}
        className="hidden"
      />

      {editSrc && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div ref={panelRef} className="w-full max-w-md rounded-xl bg-white p-4 shadow-xl dark:bg-slate-800">
            <h4 id={titleId} className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Crop image")}</h4>
            <div className="relative h-64 w-full overflow-hidden rounded-lg bg-slate-900">
              <Cropper
                image={editSrc}
                crop={crop}
                zoom={zoom}
                aspect={aspect}
                disableAutomaticStylesInjection
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            </div>
            <label className="mt-3 block text-xs text-slate-600 dark:text-slate-300">
              {t("Zoom")}
              <input
                type="range"
                min={1}
                max={3}
                step={0.01}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
                className="mt-1 w-full"
              />
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={closeEditor}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 dark:border-slate-600 dark:text-slate-300"
              >
                {t("Cancel")}
              </button>
              <button
                type="button"
                onClick={applyCrop}
                className="rounded-md bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("Apply")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
