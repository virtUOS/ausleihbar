// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Building2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { useConfirm } from "../../components/ConfirmDialog";
import { Empty } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Building } from "../types";
import type { AdminSectionProps } from "./adminTypes";
import { compareBuildingCodes } from "./BuildingSelect";
import { dangerBtn, inputCls, labelCls, primaryBtn, secondaryBtn, sectionTitleCls } from "./formStyles";

export type BuildingValues = Pick<Building, "code" | "description" | "address">;

/** Code, description and address of a building (used on its own and inside the floor form). */
export function BuildingFields({
  value,
  onChange,
  idPrefix,
}: {
  value: BuildingValues;
  onChange: (v: BuildingValues) => void;
  idPrefix: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <div>
        <label htmlFor={`${idPrefix}-code`} className={labelCls}>{t("Building code")}</label>
        <input
          id={`${idPrefix}-code`}
          required
          maxLength={20}
          value={value.code}
          onChange={(e) => onChange({ ...value, code: e.target.value })}
          placeholder={t("e.g. 15 or AX")}
          className={inputCls}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-description`} className={labelCls}>{t("Description (optional)")}</label>
        <input
          id={`${idPrefix}-description`}
          maxLength={200}
          value={value.description}
          onChange={(e) => onChange({ ...value, description: e.target.value })}
          placeholder={t("e.g. EW building")}
          className={inputCls}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-address`} className={labelCls}>{t("Address")}</label>
        <textarea
          id={`${idPrefix}-address`}
          rows={2}
          value={value.address}
          onChange={(e) => onChange({ ...value, address: e.target.value })}
          className={`${inputCls} py-2`}
        />
      </div>
    </div>
  );
}

export const trimBuilding = (v: BuildingValues): BuildingValues => ({
  code: v.code.trim(),
  description: v.description.trim(),
  address: v.address.trim(),
});

/**
 * The campus-wide building list. Every department admin may add a building;
 * changing and deleting is for app admins (`editable`). Buildings with floors
 * can't be deleted.
 */
export function BuildingsAdmin({ data, onChanged }: AdminSectionProps) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Building | "new" | null>(null);
  const [values, setValues] = useState<BuildingValues>({ code: "", description: "", address: "" });
  const [busy, setBusy] = useState(false);

  const term = query.trim().toLocaleLowerCase();
  const rows = [...data.buildings]
    .filter((b) => !term || [b.code, b.description, b.address].some((s) => s.toLocaleLowerCase().includes(term)))
    .sort((a, b) => compareBuildingCodes(a.code, b.code));

  function open(b: Building | "new") {
    setValues(b === "new" ? { code: "", description: "", address: "" } : { code: b.code, description: b.description, address: b.address });
    setEditing(b);
  }

  async function save() {
    setBusy(true);
    try {
      const v = trimBuilding(values);
      if (editing === "new") await desksApi.createBuilding(v);
      else if (editing) await desksApi.updateBuilding(editing.id, v);
      toast.success(t("Building saved."));
      setEditing(null);
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(b: Building) {
    const ok = await confirm({
      title: t("Delete building"),
      message: t("Delete the building {{code}}? Only buildings without floors can be deleted.", { code: b.code }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deleteBuilding(b.id);
      toast.success(t("Building deleted."));
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  return (
    <section aria-labelledby="buildings-title">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 id="buildings-title" className={sectionTitleCls}>
          {t("Buildings")}
        </h2>
        <button type="button" className={secondaryBtn} onClick={() => open("new")}>
          <Plus aria-hidden className="h-4 w-4" />
          {t("Add building")}
        </button>
      </div>
      <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
        {t("One list for all departments. App admins change and delete buildings.")}
      </p>
      {data.buildings.length > 6 && (
        <div className="relative mb-3 sm:max-w-sm">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            aria-label={t("Search buildings")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("Code, name or address")}
            className={`${inputCls} rounded-full pl-9`}
          />
        </div>
      )}
      {rows.length === 0 ? (
        <Empty icon={Building2} label={data.buildings.length ? t("No matches.") : t("No buildings yet.")} />
      ) : (
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
          {rows.map((b) => (
            <li key={b.id} className="flex items-center gap-3 px-3 py-2">
              <span className="w-14 shrink-0 font-semibold text-slate-900 dark:text-slate-100">{b.code}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-slate-800 dark:text-slate-100">{b.description}</span>
                {b.address && (
                  <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                    {b.address.replace(/\s*\n\s*/g, ", ")}
                  </span>
                )}
              </span>
              {b.editable && (
                <>
                  <button
                    type="button"
                    aria-label={t("Edit building {{code}}", { code: b.code })}
                    className={secondaryBtn + " !px-3"}
                    onClick={() => open(b)}
                  >
                    <Pencil aria-hidden className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={t("Delete building {{code}}", { code: b.code })}
                    className={dangerBtn + " !px-3"}
                    onClick={() => remove(b)}
                  >
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      <BottomSheet
        open={editing !== null}
        title={editing === "new" ? t("Add building") : t("Edit building")}
        onClose={() => setEditing(null)}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <BuildingFields value={values} onChange={setValues} idPrefix="building" />
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="submit" disabled={busy || !values.code.trim()} className={primaryBtn}>
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
