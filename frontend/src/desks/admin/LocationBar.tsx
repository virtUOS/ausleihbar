// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Power, Trash2 } from "lucide-react";
import { ApiError } from "../../api";
import { BottomSheet } from "../../components/BottomSheet";
import { useConfirm } from "../../components/ConfirmDialog";
import { KebabMenu, type KebabItem } from "../../components/KebabMenu";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { BuildingSelect, type BuildingOption } from "../components/BuildingSelect";
import { NameField, hasDefaultName } from "../components/NameField";
import { labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import type { Floor } from "../types";

/** Floors in their display order (position, then name). */
export const byFloorOrder = (a: Floor, b: Floor) =>
  a.position - b.position || a.name.localeCompare(b.name, undefined, { numeric: true });

/**
 * Building and floor of the workspace: the searchable building select (as on
 * the member pages) and a floor select with the floor's actions beside it
 * (app admins: rename, deactivate/reactivate, delete).
 */
export function LocationBar({
  appAdmin,
  buildings,
  buildingId,
  floors,
  floorId,
  onBuilding,
  onFloor,
  onChanged,
  onFloorDeleted,
}: {
  appAdmin: boolean;
  buildings: BuildingOption[];
  /** `undefined`: no building to choose (none yet). */
  buildingId: number | null | undefined;
  /** The floors of the chosen building, in display order. */
  floors: Floor[];
  floorId: number | null;
  onBuilding: (id: number | null) => void;
  onFloor: (id: number) => void;
  /** Reload after a floor change. */
  onChanged: () => void;
  onFloorDeleted: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const floorSelectId = useId();
  const [renaming, setRenaming] = useState(false);
  const floor = floors.find((f) => f.id === floorId) ?? null;

  async function run(job: () => Promise<unknown>, done: string): Promise<boolean> {
    try {
      await job();
      toast.success(done);
      onChanged();
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      return false;
    }
  }

  async function deactivate(f: Floor) {
    const ok = await confirm({
      title: t("Deactivate floor"),
      message: t(
        "Deactivate the floor {{name}}? Its places are retired and their upcoming reservations are cancelled.",
        { name: f.name },
      ),
      confirmLabel: t("Deactivate"),
      danger: true,
    });
    if (ok) await run(() => desksApi.updateFloor(f.id, { is_active: false }), t("Floor deactivated."));
  }

  async function remove(f: Floor) {
    const ok = await confirm({
      title: t("Delete floor"),
      message: t("Delete the floor {{name}}? Only a floor without rooms can be deleted.", { name: f.name }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deleteFloor(f.id);
      toast.success(t("Floor deleted."));
      onFloorDeleted();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast.error(`${e.message} ${t("Deactivate the floor instead.")}`);
      } else {
        toast.error(e instanceof Error ? e.message : t("The request failed."));
      }
    }
  }

  const actions: KebabItem[] = floor
    ? [
        { label: t("Rename floor"), icon: Pencil, onClick: () => setRenaming(true) },
        floor.is_active
          ? { label: t("Deactivate floor"), icon: Power, onClick: () => void deactivate(floor) }
          : {
              label: t("Reactivate floor"),
              icon: Power,
              onClick: () =>
                void run(() => desksApi.updateFloor(floor.id, { is_active: true }), t("Floor reactivated.")),
            },
        { label: t("Delete floor"), icon: Trash2, danger: true, onClick: () => void remove(floor) },
      ]
    : [];

  return (
    <div className="flex flex-wrap items-center gap-2">
      {buildingId !== undefined && (
        <BuildingSelect label={t("Building")} options={buildings} value={buildingId} onChange={onBuilding} />
      )}
      <label htmlFor={floorSelectId} className="sr-only">
        {t("Floor")}
      </label>
      <select
        id={floorSelectId}
        value={floorId ?? ""}
        disabled={floors.length === 0}
        onChange={(e) => onFloor(Number(e.target.value))}
        className="min-h-[44px] max-w-full rounded-full border border-slate-300 bg-white pl-3 pr-8 text-sm font-semibold text-slate-900 hover:border-slate-400 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-slate-500"
      >
        {floors.length === 0 && <option value="">{t("No floors yet")}</option>}
        {floors.map((f) => (
          <option key={f.id} value={f.id}>
            {f.is_active ? f.name : `${f.name} (${t("deactivated")})`}
          </option>
        ))}
      </select>
      {appAdmin && floor && <KebabMenu items={actions} label={t("Floor actions")} />}
      {floor && (
        <BottomSheet open={renaming} title={t("Rename floor")} onClose={() => setRenaming(false)}>
          <FloorForm
            floor={floor}
            onCancel={() => setRenaming(false)}
            onSave={async (v) => {
              if (await run(() => desksApi.updateFloor(floor.id, v), t("Floor saved."))) setRenaming(false);
            }}
          />
        </BottomSheet>
      )}
    </div>
  );
}

type FloorValues = { name_de: string; name_en: string | null; building: number | null };

/**
 * Name of a floor (rename) or name and building of a new floor (the building
 * is preselected; `buildings` lists the choices).
 */
export function FloorForm({
  floor,
  buildings,
  buildingId = null,
  onSave,
  onCancel,
}: {
  floor: Floor | null;
  buildings?: BuildingOption[];
  buildingId?: number | null;
  onSave: (v: FloorValues) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [nameDe, setNameDe] = useState(floor?.name_de ?? "");
  const [nameEn, setNameEn] = useState(floor?.name_en ?? "");
  const [building, setBuilding] = useState<number | null>(floor?.building ?? buildingId);
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave({ name_de: nameDe.trim(), name_en: nameEn.trim() || null, building });
        setBusy(false);
      }}
      className="flex flex-col gap-4"
    >
      <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
      {!floor && buildings && (
        <div>
          <span className={labelCls}>{t("Building")}</span>
          <BuildingSelect label={t("Building")} options={buildings} value={building} onChange={setBuilding} />
        </div>
      )}
      <div className="mt-1 flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !hasDefaultName(nameDe, nameEn)} className={primaryBtn}>
          {t("Save")}
        </button>
        <button type="button" onClick={onCancel} className={secondaryBtn}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
