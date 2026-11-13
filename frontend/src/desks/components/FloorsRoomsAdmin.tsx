// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Floor, Room, RoomKind } from "../types";
import type { AdminSectionProps } from "./adminTypes";
import { NameField } from "./NameField";
import { dangerBtn, inputCls, labelCls, primaryBtn, secondaryBtn, sectionTitleCls } from "./formStyles";

type Editing =
  | { type: "floor"; floor: Floor | null }
  | { type: "room"; room: Room | null; floorId: number }
  | null;

function useRun(onChanged: () => void) {
  const { t } = useTranslation();
  const toast = useToast();
  return async (job: () => Promise<unknown>, done: string): Promise<boolean> => {
    try {
      await job();
      toast.success(done);
      onChanged();
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
      return false;
    }
  };
}

/** Floors and their rooms of one department: create, edit, delete. */
export function FloorsRoomsAdmin({ pool, data, onChanged }: AdminSectionProps) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const run = useRun(onChanged);
  const [editing, setEditing] = useState<Editing>(null);
  const floors = data.floors
    .filter((f) => f.pool === pool)
    .sort((a, b) => a.building.localeCompare(b.building) || a.position - b.position || a.name.localeCompare(b.name));

  async function removeFloor(f: Floor) {
    const ok = await confirm({
      title: t("Delete floor"),
      message: t(
        "Delete the floor {{name}} with its rooms and places? Without reservation history it is removed for good; otherwise it is only deactivated, its places are retired and upcoming reservations are cancelled.",
        { name: f.name },
      ),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (ok) await run(() => desksApi.deleteFloor(f.id), t("Floor deleted."));
  }
  async function removeRoom(r: Room) {
    const ok = await confirm({
      title: t("Delete room"),
      message: t(
        "Delete the room {{name}} with its places? Without reservation history it is removed for good; otherwise it is only deactivated, its places are retired and upcoming reservations are cancelled.",
        { name: r.name },
      ),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (ok) await run(() => desksApi.deleteRoom(r.id), t("Room deleted."));
  }

  return (
    <section aria-labelledby="floors-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="floors-title" className={sectionTitleCls}>
          {t("Floors and rooms")}
        </h2>
        <button type="button" className={secondaryBtn} onClick={() => setEditing({ type: "floor", floor: null })}>
          <Plus aria-hidden className="h-4 w-4" />
          {t("Add floor")}
        </button>
      </div>
      <ul className="flex flex-col gap-3">
        {floors.map((f) => {
          const rooms = data.rooms.filter((r) => r.floor === f.id).sort((a, b) => a.name.localeCompare(b.name));
          return (
            <li key={f.id} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <div className="flex items-center gap-2">
                <p className="min-w-0 flex-1 font-semibold text-slate-900 dark:text-slate-100">
                  {f.building ? `${f.building} · ` : ""}
                  {f.name}
                  <span className="ml-2 text-xs font-normal text-slate-600 dark:text-slate-300">
                    {t("Position {{n}}", { n: f.position })}
                    {f.is_active ? "" : ` · ${t("Inactive")}`}
                  </span>
                </p>
                <button
                  type="button"
                  aria-label={t("Edit floor {{name}}", { name: f.name })}
                  className={secondaryBtn + " !px-3"}
                  onClick={() => setEditing({ type: "floor", floor: f })}
                >
                  <Pencil aria-hidden className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label={t("Delete floor {{name}}", { name: f.name })}
                  className={dangerBtn + " !px-3"}
                  onClick={() => removeFloor(f)}
                >
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </div>
              <ul className="mt-2 flex flex-col gap-1 border-l-2 border-slate-200 pl-3 dark:border-slate-700">
                {rooms.map((r) => (
                  <li key={r.id} className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 text-sm text-slate-800 dark:text-slate-200">
                      {r.name}
                      <span className="ml-2 text-xs text-slate-600 dark:text-slate-300">
                        {r.kind === "meeting" ? t("Meeting room area") : t("Office")}
                        {r.is_active ? "" : ` · ${t("Inactive")}`}
                      </span>
                    </span>
                    <button
                      type="button"
                      aria-label={t("Edit room {{name}}", { name: r.name })}
                      className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={() => setEditing({ type: "room", room: r, floorId: f.id })}
                    >
                      <Pencil aria-hidden className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={t("Delete room {{name}}", { name: r.name })}
                      className="flex h-11 w-11 items-center justify-center rounded-full text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-slate-800"
                      onClick={() => removeRoom(r)}
                    >
                      <Trash2 aria-hidden className="h-4 w-4" />
                    </button>
                  </li>
                ))}
                <li>
                  <button
                    type="button"
                    className="inline-flex min-h-[44px] items-center gap-2 text-sm font-semibold text-slate-700 hover:underline dark:text-slate-200"
                    onClick={() => setEditing({ type: "room", room: null, floorId: f.id })}
                  >
                    <Plus aria-hidden className="h-4 w-4" />
                    {t("Add room")}
                  </button>
                </li>
              </ul>
            </li>
          );
        })}
      </ul>

      <BottomSheet
        open={editing?.type === "floor"}
        title={editing?.type === "floor" && editing.floor ? t("Edit floor") : t("Add floor")}
        onClose={() => setEditing(null)}
      >
        {editing?.type === "floor" && (
          <FloorForm
            floor={editing.floor}
            onCancel={() => setEditing(null)}
            onSave={async (v) => {
              const ok = await run(
                () =>
                  editing.floor
                    ? desksApi.updateFloor(editing.floor.id, v)
                    : desksApi.createFloor({ ...v, pool }),
                t("Floor saved."),
              );
              if (ok) setEditing(null);
            }}
          />
        )}
      </BottomSheet>
      <BottomSheet
        open={editing?.type === "room"}
        title={editing?.type === "room" && editing.room ? t("Edit room") : t("Add room")}
        onClose={() => setEditing(null)}
      >
        {editing?.type === "room" && (
          <RoomForm
            room={editing.room}
            onCancel={() => setEditing(null)}
            onSave={async (v) => {
              const ok = await run(
                () =>
                  editing.room
                    ? desksApi.updateRoom(editing.room.id, v)
                    : desksApi.createRoom({ ...v, floor: editing.floorId }),
                t("Room saved."),
              );
              if (ok) setEditing(null);
            }}
          />
        )}
      </BottomSheet>
    </section>
  );
}

function ActiveToggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <label className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
      <input type="checkbox" className="h-5 w-5" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {t("Active (bookable)")}
    </label>
  );
}

function Actions({ onCancel, disabled }: { onCancel: () => void; disabled: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      <button type="submit" disabled={disabled} className={primaryBtn}>
        {t("Save")}
      </button>
      <button type="button" onClick={onCancel} className={secondaryBtn}>
        {t("Cancel")}
      </button>
    </div>
  );
}

function FloorForm({
  floor,
  onSave,
  onCancel,
}: {
  floor: Floor | null;
  onSave: (v: {
    name_de: string;
    name_en: string | null;
    building: string;
    position: number;
    is_active: boolean;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [nameDe, setNameDe] = useState(floor?.name_de ?? "");
  const [nameEn, setNameEn] = useState(floor?.name_en ?? "");
  const [active, setActive] = useState(floor?.is_active ?? true);
  const [building, setBuilding] = useState(floor?.building ?? "");
  const [position, setPosition] = useState(floor?.position ?? 0);
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave({
          name_de: nameDe.trim(),
          name_en: nameEn.trim() || null,
          building: building.trim(),
          position,
          is_active: active,
        });
        setBusy(false);
      }}
      className="flex flex-col gap-4"
    >
      <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
      <div>
        <label htmlFor="floor-building" className={labelCls}>{t("Building")}</label>
        <input id="floor-building" maxLength={100} value={building} onChange={(e) => setBuilding(e.target.value)} className={inputCls} />
      </div>
      <div>
        <label htmlFor="floor-position" className={labelCls}>{t("Position (order)")}</label>
        <input
          id="floor-position"
          type="number"
          min={0}
          value={position}
          onChange={(e) => setPosition(Number(e.target.value))}
          className={inputCls}
        />
      </div>
      <ActiveToggle checked={active} onChange={setActive} />
      <Actions onCancel={onCancel} disabled={busy || !nameDe.trim()} />
    </form>
  );
}

function RoomForm({
  room,
  onSave,
  onCancel,
}: {
  room: Room | null;
  onSave: (v: {
    name_de: string;
    name_en: string | null;
    kind: RoomKind;
    is_active: boolean;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [nameDe, setNameDe] = useState(room?.name_de ?? "");
  const [nameEn, setNameEn] = useState(room?.name_en ?? "");
  const [active, setActive] = useState(room?.is_active ?? true);
  const [kind, setKind] = useState<RoomKind>(room?.kind ?? "office");
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave({ name_de: nameDe.trim(), name_en: nameEn.trim() || null, kind, is_active: active });
        setBusy(false);
      }}
      className="flex flex-col gap-4"
    >
      <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
      <div>
        <label htmlFor="room-kind" className={labelCls}>{t("Kind")}</label>
        <select id="room-kind" value={kind} onChange={(e) => setKind(e.target.value as RoomKind)} className={inputCls}>
          <option value="office">{t("Office")}</option>
          <option value="meeting">{t("Meeting room area")}</option>
        </select>
      </div>
      <ActiveToggle checked={active} onChange={setActive} />
      <Actions onCancel={onCancel} disabled={busy || !nameDe.trim()} />
    </form>
  );
}
