// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { MoreVertical, Pencil, Power, Trash2 } from "lucide-react";
import { ApiError } from "../../api";
import { BottomSheet } from "../../components/BottomSheet";
import { useConfirm } from "../../components/ConfirmDialog";
import { KebabMenu, type KebabItem } from "../../components/KebabMenu";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { BuildingDialog } from "../components/BuildingDialog";
import { BuildingSelect, type BuildingOption } from "../components/BuildingSelect";
import { NameField, hasDefaultName } from "../components/NameField";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import type { Building, Floor } from "../types";

/** Floors in their display order (position, then name). */
export const byFloorOrder = (a: Floor, b: Floor) =>
  a.position - b.position || a.name.localeCompare(b.name, undefined, { numeric: true });

/** 44 px icon trigger of the action menus (building, floor, room, place). */
export const actionsTrigger = {
  icon: MoreVertical,
  className:
    "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100",
};

/**
 * Building and floor of the workspace: the searchable building select (as on
 * the member pages) with the building's actions (app admins: edit, delete)
 * and a floor select with the floor's actions (app admins: edit name,
 * building and order, deactivate/reactivate, delete).
 */
export function LocationBar({
  appAdmin,
  buildings,
  buildingId,
  building,
  floorBuildings,
  floors,
  floorId,
  onBuilding,
  onFloor,
  onChanged,
  onFloorDeleted,
  onFloorSaved,
  onBuildingDeleted,
}: {
  appAdmin: boolean;
  buildings: BuildingOption[];
  /** `undefined`: no building to choose (none yet). */
  buildingId: number | null | undefined;
  /** The chosen building (absent for "without building"). */
  building?: Building;
  /** Building choices when editing a floor. */
  floorBuildings: BuildingOption[];
  /** The floors of the chosen building, in display order. */
  floors: Floor[];
  floorId: number | null;
  onBuilding: (id: number | null) => void;
  onFloor: (id: number) => void;
  /** Reload after a floor change. */
  onChanged: () => void;
  onFloorDeleted: () => void;
  /** After editing a floor (it may have moved to another building). */
  onFloorSaved: (floor: Floor) => void;
  onBuildingDeleted: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const floorSelectId = useId();
  const [editingFloor, setEditingFloor] = useState(false);
  const [editingBuilding, setEditingBuilding] = useState(false);
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

  async function removeBuilding(b: Building) {
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
      onBuildingDeleted();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  const buildingActions: KebabItem[] = building
    ? [
        { label: t("Edit building"), icon: Pencil, onClick: () => setEditingBuilding(true) },
        { label: t("Delete building"), icon: Trash2, danger: true, onClick: () => void removeBuilding(building) },
      ]
    : [];

  const actions: KebabItem[] = floor
    ? [
        { label: t("Edit floor"), icon: Pencil, onClick: () => setEditingFloor(true) },
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
      {appAdmin && building?.editable && (
        <KebabMenu items={buildingActions} label={t("Building actions")} trigger={actionsTrigger} />
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
      {appAdmin && floor && <KebabMenu items={actions} label={t("Floor actions")} trigger={actionsTrigger} />}
      {floor && (
        <BottomSheet open={editingFloor} title={t("Edit floor")} onClose={() => setEditingFloor(false)}>
          <FloorForm
            floor={floor}
            buildings={floorBuildings}
            onCancel={() => setEditingFloor(false)}
            onSave={async (v) => {
              try {
                const saved = await desksApi.updateFloor(floor.id, v);
                toast.success(t("Floor saved."));
                setEditingFloor(false);
                onFloorSaved(saved);
              } catch (e) {
                toast.error(e instanceof Error ? e.message : t("The request failed."));
              }
            }}
          />
        </BottomSheet>
      )}
      {building && (
        <BuildingDialog
          open={editingBuilding}
          building={building}
          onClose={() => setEditingBuilding(false)}
          onSaved={() => {
            setEditingBuilding(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

type FloorValues = { name_de: string; name_en: string | null; building: number | null; position?: number };

/**
 * Name and building of a new floor (the building is preselected; `buildings`
 * lists the choices), or name, building and order of an existing one.
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
  const [building, setBuilding] = useState<number | null>(floor ? floor.building : buildingId);
  const [position, setPosition] = useState(floor?.position ?? 0);
  const positionId = useId();
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave({
          name_de: nameDe.trim(),
          name_en: nameEn.trim() || null,
          building,
          ...(floor ? { position } : {}),
        });
        setBusy(false);
      }}
      className="flex flex-col gap-4"
    >
      <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
      {buildings && (
        <div>
          <span className={labelCls}>{t("Building")}</span>
          <BuildingSelect label={t("Building")} options={buildings} value={building} onChange={setBuilding} />
        </div>
      )}
      {floor && (
        <div>
          <label htmlFor={positionId} className={labelCls}>{t("Position (order)")}</label>
          <input
            id={positionId}
            type="number"
            min={0}
            value={position}
            onChange={(e) => setPosition(Number(e.target.value))}
            className={inputCls}
          />
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
