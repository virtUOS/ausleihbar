// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";

/** What the parent form should do with the image when it saves. */
export type ImageAction =
  | { kind: "set"; blob: Blob }
  | { kind: "clear" }
  | null;

/** Draw the selected crop area onto a canvas and export it as a JPEG blob. */
async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(area.width);
  canvas.height = Math.round(area.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported.");
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

  const onCropComplete = useCallback((_: Area, pixels: Area) => setArea(pixels), []);

  function pickFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setEditSrc(URL.createObjectURL(file));
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
      <input
        ref={fileInput}
        type="file"
        accept="image/*"
        onChange={pickFile}
        className="hidden"
      />

      {editSrc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-4 shadow-xl dark:bg-slate-800">
            <h4 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Crop image")}</h4>
            <div className="relative h-64 w-full overflow-hidden rounded-lg bg-slate-900">
              <Cropper
                image={editSrc}
                crop={crop}
                zoom={zoom}
                aspect={aspect}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            </div>
            <label className="mt-3 block text-xs text-slate-500 dark:text-slate-400">
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
