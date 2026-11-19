// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Pencil, Sparkles, Trash2 } from "lucide-react";
import { ApiError } from "../../api";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Feature } from "../types";
import { FeatureDialog } from "./FeatureDialog";

const iconBtn =
  "inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800";

/**
 * Collapsible "Ausstattung" section at the bottom of the workspace: all
 * campus-wide equipment with picture, name and description excerpt. App
 * admins edit and delete it.
 */
export function FeaturesList({
  features,
  appAdmin,
  onChanged,
}: {
  features: Feature[];
  appAdmin: boolean;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Feature | null>(null);

  async function remove(f: Feature) {
    const ok = await confirm({
      title: t("Delete feature"),
      message: t("Delete the feature {{name}}? Only equipment no place uses can be deleted.", { name: f.name }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deleteFeature(f.id);
      toast.success(t("Feature deleted."));
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast.error(t("This equipment is still in use."));
      } else if (e instanceof ApiError && e.status === 404) {
        // Already removed elsewhere: show the current list.
        toast.error(e.message);
        onChanged();
      } else {
        toast.error(e instanceof Error ? e.message : t("The request failed."));
      }
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-2xl px-4 py-2 text-left"
      >
        <span className="inline-flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100">
          <Sparkles aria-hidden className="h-5 w-5" />
          {t("Equipment")}
          <span className="text-sm font-normal text-slate-600 dark:text-slate-300">({features.length})</span>
        </span>
        <ChevronDown aria-hidden className={`h-5 w-5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul className="divide-y divide-slate-200 border-t border-slate-200 dark:divide-slate-700 dark:border-slate-700">
          {features.length === 0 && (
            <li className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">{t("No equipment yet.")}</li>
          )}
          {features.map((f) => (
            <li key={f.id} className="flex items-center gap-3 px-4 py-2">
              {f.images[0] ? (
                <img src={f.images[0].image} alt="" className="h-12 w-12 shrink-0 rounded-lg object-cover" />
              ) : (
                <span
                  aria-hidden
                  className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-800"
                >
                  <Sparkles className="h-5 w-5" />
                </span>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{f.name}</p>
                {f.description && (
                  <p className="line-clamp-2 text-xs text-slate-600 dark:text-slate-300">{f.description}</p>
                )}
              </div>
              {appAdmin && (
                <>
                  <button
                    type="button"
                    className={iconBtn}
                    aria-label={t("Edit feature {{name}}", { name: f.name })}
                    onClick={() => setEditing(f)}
                  >
                    <Pencil aria-hidden className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    className={iconBtn}
                    aria-label={t("Delete feature {{name}}", { name: f.name })}
                    onClick={() => void remove(f)}
                  >
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <FeatureDialog
          open
          feature={editing}
          appAdmin={appAdmin}
          onClose={() => setEditing(null)}
          onSaved={onChanged}
        />
      )}
    </section>
  );
}
