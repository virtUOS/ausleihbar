// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BottomSheet } from "../../components/BottomSheet";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import type { PersonChoice, Place, PlaceInput, PlaceKind } from "../types";
import type { PlacesAdminData } from "./adminTypes";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "./formStyles";
import { NameField } from "./NameField";
import { PersonPicker } from "./PersonPicker";

/** Create / edit a place: room, kind, name, capacity (meeting rooms), equipment,
 *  restriction groups, special flag, fixed owner (desks), active. */
export function PlaceFormDialog({
  open,
  pool,
  data,
  place,
  onClose,
  onSave,
}: {
  open: boolean;
  pool: number;
  data: PlacesAdminData;
  /** null = create. */
  place: Place | null;
  onClose: () => void;
  onSave: (input: PlaceInput) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={place ? t("Edit place") : t("Add place")} onClose={onClose}>
      {open && <PlaceForm key={place?.id ?? "new"} pool={pool} data={data} place={place} onClose={onClose} onSave={onSave} />}
    </BottomSheet>
  );
}

function PlaceForm({
  pool,
  data,
  place,
  onClose,
  onSave,
}: {
  pool: number;
  data: PlacesAdminData;
  place: Place | null;
  onClose: () => void;
  onSave: (input: PlaceInput) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const groups = useFetch(() => desksApi.accessGroups(pool), [pool]);
  // Active rows, plus the place's own room/floor when it is deactivated.
  const floors = data.floors.filter((f) => f.pool === pool && (f.is_active || data.rooms.some((r) => r.id === place?.room && r.floor === f.id)));
  const rooms = data.rooms.filter((r) => floors.some((f) => f.id === r.floor) && (r.is_active || r.id === place?.room));
  const features = data.features.filter((f) => f.pool === pool);

  const [room, setRoom] = useState<number | "">(place?.room ?? rooms[0]?.id ?? "");
  const [kind, setKind] = useState<PlaceKind>(place?.kind ?? "desk");
  const [nameDe, setNameDe] = useState(place?.name_de ?? "");
  const [nameEn, setNameEn] = useState(place?.name_en ?? "");
  const [capacity, setCapacity] = useState<number | "">(place?.capacity ?? "");
  const [featureIds, setFeatureIds] = useState<number[]>(place?.features ?? []);
  const [groupIds, setGroupIds] = useState<number[]>(place?.access_groups ?? []);
  const [special, setSpecial] = useState(place?.is_special ?? false);
  const [owner, setOwner] = useState<PersonChoice | null>(
    place?.fixed_owner ? { id: place.fixed_owner, name: place.fixed_owner_name ?? `#${place.fixed_owner}` } : null,
  );
  const [active, setActive] = useState(place?.is_active ?? true);
  const [busy, setBusy] = useState(false);

  const toggle = (list: number[], id: number) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  const meeting = kind === "meeting_room";
  const valid = room !== "" && nameDe.trim() !== "" && (!meeting || Number(capacity) > 0);

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (room === "") return;
        setBusy(true);
        await onSave({
          room,
          kind,
          name_de: nameDe.trim(),
          name_en: nameEn.trim() || null,
          capacity: meeting ? Number(capacity) : null,
          features: featureIds,
          access_groups: groupIds,
          is_special: special,
          fixed_owner: meeting ? null : (owner?.id ?? null),
          is_active: active,
        });
        setBusy(false);
      }}
      className="flex flex-col gap-4"
    >
      <div>
        <label htmlFor="place-room" className={labelCls}>{t("Room")}</label>
        <select
          id="place-room"
          required
          value={room}
          onChange={(e) => setRoom(Number(e.target.value))}
          className={inputCls}
        >
          {floors.map((f) => (
            <optgroup key={f.id} label={[f.building, f.name].filter(Boolean).join(" · ")}>
              {rooms.filter((r) => r.floor === f.id).map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="place-kind" className={labelCls}>{t("Kind")}</label>
        <select id="place-kind" value={kind} onChange={(e) => setKind(e.target.value as PlaceKind)} className={inputCls}>
          <option value="desk">{t("Desk")}</option>
          <option value="meeting_room">{t("Meeting room")}</option>
        </select>
      </div>
      <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
      {meeting && (
        <div>
          <label htmlFor="place-capacity" className={labelCls}>{t("Capacity (persons)")}</label>
          <input
            id="place-capacity"
            type="number"
            min={1}
            required
            value={capacity}
            onChange={(e) => setCapacity(e.target.value === "" ? "" : Number(e.target.value))}
            className={inputCls}
          />
        </div>
      )}

      <fieldset>
        <legend className={labelCls}>{t("Equipment")}</legend>
        {features.length === 0 ? (
          <p className="text-xs text-slate-600 dark:text-slate-300">{t("No equipment features yet.")}</p>
        ) : (
          <div className="flex flex-col">
            {features.map((f) => (
              <label key={f.id} className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
                <input type="checkbox" className="h-5 w-5" checked={featureIds.includes(f.id)} onChange={() => setFeatureIds((l) => toggle(l, f.id))} />
                {f.name}
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <fieldset>
        <legend className={labelCls}>{t("Restrict to groups")}</legend>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">
          {t("Without a group every member of the department may book this place.")}
        </p>
        {!groups.data ? (
          <p className="text-xs text-slate-600 dark:text-slate-300">{t("Loading…")}</p>
        ) : (
          <div className="flex max-h-48 flex-col overflow-y-auto">
            {[...groups.data].sort((a, b) => Number(b.in_pool) - Number(a.in_pool)).map((g) => (
              <label key={g.id} className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
                <input type="checkbox" className="h-5 w-5" checked={groupIds.includes(g.id)} onChange={() => setGroupIds((l) => toggle(l, g.id))} />
                <span>{g.name}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <label className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
        <input type="checkbox" className="h-5 w-5" checked={special} onChange={(e) => setSpecial(e.target.checked)} />
        <span>
          {t("Special place")}
          <span className="block text-xs text-slate-600 dark:text-slate-300">{t("Reported individually in the statistics.")}</span>
        </span>
      </label>

      {!meeting && (
        <div>
          <PersonPicker pool={pool} value={owner} onChange={setOwner} label={t("Fixed owner (optional)")} />
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {t("A fixed desk is reserved for its owner whenever they are present.")}
          </p>
        </div>
      )}

      <label className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
        <input type="checkbox" className="h-5 w-5" checked={active} onChange={(e) => setActive(e.target.checked)} />
        {t("Active (bookable)")}
      </label>

      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !valid} className={primaryBtn}>{t("Save")}</button>
        <button type="button" onClick={onClose} className={secondaryBtn}>{t("Cancel")}</button>
      </div>
    </form>
  );
}
