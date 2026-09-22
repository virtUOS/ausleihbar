// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ImagePlus } from "lucide-react";
import type { ProductImage } from "../types";

/** One gallery slot: an already-saved image or a newly picked file. */
export interface GalleryItem {
  key: string;
  /** Set for images already stored on the server. */
  existingId?: number;
  /** Set for newly picked/dropped files (not yet uploaded). */
  file?: File;
  /** Display URL (stored URL or an object URL for a new file). */
  url: string;
}

/** What the form should apply after saving the product. */
export interface GalleryPlan {
  order: GalleryItem[];
  deletes: number[];
}

let counter = 0;
const nextKey = () => `n${counter++}`;

/**
 * Multi-image gallery editor: pick via dialog or drop files onto the zone,
 * remove, and drag thumbnails to reorder (the first is the cover). Holds local
 * state and reports a plan via `onChange`; the form applies it after save.
 */
export function ProductImagesField({
  initialImages,
  onChange,
}: {
  initialImages: ProductImage[];
  onChange: (plan: GalleryPlan) => void;
}) {
  const { t } = useTranslation();
  const [items, setItems] = useState<GalleryItem[]>(() =>
    initialImages.map((img) => ({ key: `e${img.id}`, existingId: img.id, url: img.image })),
  );
  const [deletes, setDeletes] = useState<number[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const dragKey = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Report the current plan whenever it changes.
  useEffect(() => {
    onChange({ order: items, deletes });
  }, [items, deletes, onChange]);

  // Revoke object URLs on unmount.
  useEffect(
    () => () => {
      items.forEach((i) => i.file && URL.revokeObjectURL(i.url));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  function addFiles(files: FileList | File[]) {
    const picked = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (!picked.length) return;
    setItems((prev) => [
      ...prev,
      ...picked.map((file) => ({ key: nextKey(), file, url: URL.createObjectURL(file) })),
    ]);
  }

  function remove(key: string) {
    setItems((prev) => {
      const item = prev.find((i) => i.key === key);
      if (item?.file) URL.revokeObjectURL(item.url);
      if (item?.existingId) setDeletes((d) => [...d, item.existingId!]);
      return prev.filter((i) => i.key !== key);
    });
  }

  function onDropFiles(event: React.DragEvent) {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer.files?.length) addFiles(event.dataTransfer.files);
  }

  // Thumbnail reordering (drag a thumbnail onto another).
  function onThumbDragStart(key: string) {
    dragKey.current = key;
  }
  function onThumbDragEnter(key: string) {
    const from = dragKey.current;
    if (from === null || from === key) return;
    setItems((prev) => {
      const fromIndex = prev.findIndex((i) => i.key === from);
      const toIndex = prev.findIndex((i) => i.key === key);
      if (fromIndex < 0 || toIndex < 0) return prev;
      const next = prev.slice();
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
  }

  return (
    <div>
      <div
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDropFiles}
        className={`flex min-h-[88px] cursor-pointer flex-wrap items-center gap-2 rounded-lg border-2 border-dashed p-3 ${
          dragOver ? "border-slate-900 bg-slate-50 dark:bg-slate-800/50" : "border-slate-300 dark:border-slate-600"
        }`}
      >
        {items.map((item, index) => (
          <div
            key={item.key}
            draggable
            onDragStart={(e) => {
              e.stopPropagation();
              onThumbDragStart(item.key);
            }}
            onDragEnter={() => onThumbDragEnter(item.key)}
            onDragOver={(e) => e.preventDefault()}
            onClick={(e) => e.stopPropagation()}
            title={t("Drag to reorder")}
            className="group relative h-20 w-20 shrink-0 cursor-move overflow-hidden rounded-md border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"
          >
            <img src={item.url} alt="" className="h-full w-full object-cover" />
            {index === 0 && (
              <span className="absolute bottom-0 left-0 right-0 bg-slate-900/70 text-center text-[10px] font-medium text-white">
                {t("Cover")}
              </span>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                remove(item.key);
              }}
              aria-label={t("Remove")}
              className="absolute right-0 top-0 flex h-5 w-5 items-center justify-center rounded-bl bg-black/60 text-[11px] text-white opacity-0 group-hover:opacity-100"
            >
              ✕
            </button>
          </div>
        ))}
        <span className="flex items-center gap-2 px-2 text-xs text-slate-600 dark:text-slate-300">
          <ImagePlus aria-hidden className="h-5 w-5 text-slate-400" />
          {t("Drop images here or click to upload (multiple allowed)")}
        </span>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept="image/*"
        multiple
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
          e.target.value = "";
        }}
        className="hidden"
      />
    </div>
  );
}
