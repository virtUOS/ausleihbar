// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { TranslatableField } from "@basicbar/ui";
import { BottomSheet } from "../../components/BottomSheet";
import {
  ProductImagesField,
  applyGalleryPlan,
  galleryPlanDirty,
  type GalleryPlan,
} from "../../components/ProductImagesField";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { NameField, hasDefaultName } from "../components/NameField";
import { inputCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import type { Feature } from "../types";

/**
 * Adds or edits a piece of (campus-wide) equipment. Everyone who may create
 * equipment enters the name; app admins also maintain description and
 * pictures (department admins are told who does).
 */
export function FeatureDialog({
  open,
  feature,
  appAdmin,
  onClose,
  onSaved,
}: {
  open: boolean;
  /** The equipment to edit (app admins); absent: a new one. */
  feature?: Feature;
  appAdmin: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={feature ? t("Edit feature") : t("New equipment")} onClose={onClose}>
      <FeatureForm feature={feature} appAdmin={appAdmin} onClose={onClose} onSaved={onSaved} />
    </BottomSheet>
  );
}

function FeatureForm({
  feature,
  appAdmin,
  onClose,
  onSaved,
}: {
  feature?: Feature;
  appAdmin: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const [nameDe, setNameDe] = useState(feature?.name_de ?? "");
  const [nameEn, setNameEn] = useState(feature?.name_en ?? "");
  const [descDe, setDescDe] = useState(feature?.description_de ?? "");
  const [descEn, setDescEn] = useState(feature?.description_en ?? "");
  const [busy, setBusy] = useState(false);
  const initialImages = feature?.images ?? [];
  const galleryPlan = useRef<GalleryPlan>({ order: [], deletes: [] });
  const onGalleryChange = useCallback((plan: GalleryPlan) => {
    galleryPlan.current = plan;
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const names = { name_de: nameDe.trim(), name_en: nameEn.trim() || null };
      const data = appAdmin
        ? { ...names, description_de: descDe.trim(), description_en: descEn.trim() || null }
        : names;
      const saved = feature ? await desksApi.updateFeature(feature.id, data) : await desksApi.createFeature(data);
      let imagesFailed = false;
      if (appAdmin && galleryPlanDirty(galleryPlan.current, initialImages)) {
        try {
          await applyGalleryPlan(galleryPlan.current, desksApi.featureGalleryOps(saved.id));
        } catch {
          imagesFailed = true;
        }
      }
      if (imagesFailed) {
        // The equipment itself is kept; only the pictures need another try.
        toast.warning(t("Equipment saved, but its pictures could not be saved completely. Open it again to retry."));
      } else {
        toast.success(t("Feature saved."));
      }
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
      {appAdmin ? (
        <>
          <TranslatableField
            label={t("Description")}
            values={{ de: descDe, en: descEn }}
            onChange={(lang, v) => (lang === "de" ? setDescDe(v) : setDescEn(v))}
            inputClass={inputCls}
            multiline
            rows={3}
          />
          <div role="group" aria-label={t("Pictures")}>
            <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Pictures")}</p>
            <ProductImagesField initialImages={initialImages} onChange={onGalleryChange} />
          </div>
        </>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {t("An app admin maintains description and pictures.")}
        </p>
      )}
      <div className="mt-1 flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !hasDefaultName(nameDe, nameEn)} className={primaryBtn}>
          {t("Save")}
        </button>
        <button type="button" onClick={onClose} className={secondaryBtn}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
