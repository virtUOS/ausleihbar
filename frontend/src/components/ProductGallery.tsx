// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ProductImage } from "../types";
import { ImageLightbox } from "./ImageLightbox";

/** Product image gallery: a large main image with a thumbnail row to switch.
 *  Clicking the main image opens a full-screen viewer to page through them.
 *  Falls back to a symbol when the product has no images. */
export function ProductGallery({
  images,
  fallback,
}: {
  images: ProductImage[];
  fallback: React.ReactNode;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState(0);
  const [lightbox, setLightbox] = useState(false);

  if (images.length === 0) {
    return (
      <div className="mx-auto mt-2 flex aspect-square w-full max-w-xs items-center justify-center overflow-hidden rounded-xl bg-slate-100 text-6xl dark:bg-slate-800">
        <span aria-hidden>{fallback}</span>
      </div>
    );
  }

  const current = Math.min(selected, images.length - 1);
  const main = images[current];
  return (
    <div className="mx-auto mt-2 w-full max-w-xs">
      <button
        type="button"
        onClick={() => setLightbox(true)}
        aria-label={t("View image larger")}
        className="flex aspect-square w-full cursor-zoom-in items-center justify-center overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800"
      >
        <img src={main.image} alt="" className="h-full w-full object-cover" />
      </button>
      {lightbox && (
        <ImageLightbox
          images={images.map((i) => i.image)}
          startIndex={current}
          onClose={() => setLightbox(false)}
        />
      )}
      {images.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {images.map((img, i) => (
            <button
              key={img.id}
              type="button"
              onClick={() => setSelected(i)}
              className={`h-14 w-14 overflow-hidden rounded-md border-2 ${
                i === selected ? "border-slate-900 dark:border-slate-100" : "border-transparent"
              }`}
            >
              <img src={img.image} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
