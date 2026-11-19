// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Sparkles, Trash2 } from "lucide-react";
import { ApiError } from "../../api";
import { useConfirm } from "../../components/ConfirmDialog";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { secondaryBtn, sectionTitleCls } from "../components/formStyles";
import type { Feature } from "../types";
import { FeatureDialog } from "./FeatureDialog";

const iconBtn =
  "inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800";

/**
 * The "Ausstattung" section of the settings tab: all campus-wide equipment
 * with picture, name and description excerpt. Department admins add names;
 * app admins also edit (description, pictures) and delete.
 */
export function FeaturesList({ appAdmin }: { appAdmin: boolean }) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [version, setVersion] = useState(0);
  const onChanged = () => setVersion((n) => n + 1);
  const fetched = useFetch(() => desksApi.features(), [version]);
  const [editing, setEditing] = useState<Feature | null>(null);
  const [adding, setAdding] = useState(false);

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

  const features = fetched.data;
  return (
    <section aria-labelledby="set-equipment">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="set-equipment" className={sectionTitleCls}>
            {t("Equipment")}
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-300">{t("Applies to all pools.")}</p>
        </div>
        <button type="button" onClick={() => setAdding(true)} className={secondaryBtn}>
          <span aria-hidden className="text-base leading-none">
            +
          </span>
          {t("New equipment")}
        </button>
      </div>
      {fetched.error ? (
        <ErrorBox message={fetched.error} />
      ) : !features ? (
        <Loading />
      ) : (
        <ul className="mt-3 divide-y divide-slate-200 rounded-xl border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
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
      {adding && <FeatureDialog open appAdmin={appAdmin} onClose={() => setAdding(false)} onSaved={onChanged} />}
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
