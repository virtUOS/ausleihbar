// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Feature } from "../types";
import type { AdminSectionProps } from "./adminTypes";
import { inputCls, labelCls, primaryBtn, secondaryBtn, sectionTitleCls } from "./formStyles";

/** Equipment features of the department (e.g. "Monitor", "Height-adjustable"). */
export function FeaturesAdmin({ pool, data, onChanged }: AdminSectionProps) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = useState<{ feature: Feature | null } | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const features = data.features
    .filter((f) => f.pool === pool)
    .sort((a, b) => a.name.localeCompare(b.name));

  function open(feature: Feature | null) {
    setName(feature?.name ?? "");
    setEditing({ feature });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    try {
      if (editing.feature) await desksApi.updateFeature(editing.feature.id, { name: name.trim() });
      else await desksApi.createFeature({ pool, name: name.trim() });
      toast.success(t("Feature saved."));
      setEditing(null);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(f: Feature) {
    const ok = await confirm({
      title: t("Delete feature"),
      message: t("Delete the feature {{name}}? It is removed from all places that have it.", { name: f.name }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deleteFeature(f.id);
      toast.success(t("Feature deleted."));
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("The request failed."));
    }
  }

  return (
    <section aria-labelledby="features-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="features-title" className={sectionTitleCls}>
          {t("Equipment")}
        </h2>
        <button type="button" className={secondaryBtn} onClick={() => open(null)}>
          <Plus aria-hidden className="h-4 w-4" />
          {t("Add feature")}
        </button>
      </div>
      {features.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("No equipment features yet.")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {features.map((f) => (
            <li key={f.id} className="flex items-center gap-2 rounded-xl border border-slate-200 pl-4 dark:border-slate-700">
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900 dark:text-slate-100">{f.name}</span>
              <button
                type="button"
                aria-label={t("Edit feature {{name}}", { name: f.name })}
                className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => open(f)}
              >
                <Pencil aria-hidden className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label={t("Delete feature {{name}}", { name: f.name })}
                className="flex h-11 w-11 items-center justify-center rounded-full text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-slate-800"
                onClick={() => remove(f)}
              >
                <Trash2 aria-hidden className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <BottomSheet
        open={editing !== null}
        title={editing?.feature ? t("Edit feature") : t("Add feature")}
        onClose={() => setEditing(null)}
      >
        <form onSubmit={save} className="flex flex-col gap-4">
          <div>
            <label htmlFor="feature-name" className={labelCls}>{t("Name")}</label>
            <input
              id="feature-name"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputCls}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={busy || !name.trim()} className={primaryBtn}>
              {t("Save")}
            </button>
            <button type="button" onClick={() => setEditing(null)} className={secondaryBtn}>
              {t("Cancel")}
            </button>
          </div>
        </form>
      </BottomSheet>
    </section>
  );
}
