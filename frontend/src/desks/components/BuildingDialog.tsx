// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BottomSheet } from "../../components/BottomSheet";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Building } from "../types";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "./formStyles";

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
 * Adds a campus-wide building (every department admin may) or edits
 * `building` (app admins). `onSaved` gets the saved building.
 */
export function BuildingDialog({
  open,
  building,
  savedMessage,
  onClose,
  onSaved,
}: {
  open: boolean;
  building?: Building;
  /** Toast after saving (default "Building saved."). */
  savedMessage?: string;
  onClose: () => void;
  onSaved: (building: Building) => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={building ? t("Edit building") : t("Add building")} onClose={onClose}>
      <BuildingForm building={building} savedMessage={savedMessage} onClose={onClose} onSaved={onSaved} />
    </BottomSheet>
  );
}

function BuildingForm({
  building,
  savedMessage,
  onClose,
  onSaved,
}: {
  building?: Building;
  savedMessage?: string;
  onClose: () => void;
  onSaved: (building: Building) => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const [values, setValues] = useState<BuildingValues>({
    code: building?.code ?? "",
    description: building?.description ?? "",
    address: building?.address ?? "",
  });
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const v = trimBuilding(values);
      const saved = building ? await desksApi.updateBuilding(building.id, v) : await desksApi.createBuilding(v);
      toast.success(savedMessage ?? t("Building saved."));
      onSaved(saved);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
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
        <button type="button" onClick={onClose} className={secondaryBtn}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
