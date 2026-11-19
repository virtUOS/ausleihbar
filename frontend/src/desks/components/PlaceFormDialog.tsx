// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AccessGroupCheckboxes } from "../../components/AccessGroupCheckboxes";
import { BottomSheet } from "../../components/BottomSheet";
import { WarningNotice } from "../../components/WarningNotice";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import type { PersonChoice, Place, PlaceInput, PlaceKind, Room } from "../types";
import type { PlacesAdminData } from "./adminTypes";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "./formStyles";
import { NameField, hasDefaultName } from "./NameField";
import { PersonPicker } from "./PersonPicker";

/** Create / edit a place: room, kind, name, capacity (meeting rooms), equipment,
 *  restriction groups, special flag, fixed owner (desks), active. */
export function PlaceFormDialog({
  open,
  pool,
  data,
  place,
  initialRoom,
  initialName,
  initialKind,
  initialCapacity,
  error,
  onClose,
  onSave,
}: {
  open: boolean;
  pool: number;
  data: PlacesAdminData;
  /** null = create. */
  place: Place | null;
  /** Create only: the room and German name to start with. */
  initialRoom?: number;
  initialName?: string;
  initialKind?: PlaceKind;
  initialCapacity?: number | null;
  /** The last save's error (e.g. the backend's refusal), shown in the form. */
  error?: string | null;
  onClose: () => void;
  onSave: (input: PlaceInput) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={place ? t("Edit place") : t("Add place")} onClose={onClose}>
      {open && (
        <PlaceForm
          key={place?.id ?? "new"}
          pool={pool}
          data={data}
          place={place}
          initialRoom={initialRoom}
          initialName={initialName}
          initialKind={initialKind}
          initialCapacity={initialCapacity}
          error={error ?? null}
          onClose={onClose}
          onSave={onSave}
        />
      )}
    </BottomSheet>
  );
}

function PlaceForm({
  pool,
  data,
  place,
  initialRoom,
  initialName,
  initialKind,
  initialCapacity,
  error,
  onClose,
  onSave,
}: {
  pool: number;
  data: PlacesAdminData;
  place: Place | null;
  initialRoom?: number;
  initialName?: string;
  initialKind?: PlaceKind;
  initialCapacity?: number | null;
  error: string | null;
  onClose: () => void;
  onSave: (input: PlaceInput) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const groups = useFetch(() => desksApi.accessGroups(pool), [pool]);
  // Active rooms of this department on active floors, plus the place's own
  // room (also when deactivated or of another department). An unassigned
  // place (or a new one in an unassigned room) stays unassigned: it only
  // moves between the unassigned rooms of its floor, never silently into
  // the current department's rooms (`pool` is just the fallback then).
  const activeFloor = new Set(data.floors.filter((f) => f.is_active).map((f) => f.id));
  const ownRoom = data.rooms.find((r) => r.id === (place?.room ?? initialRoom));
  const unassigned = place ? place.pool === null : ownRoom?.pool === null;
  const movable = (r: Room) => (unassigned ? r.pool === null && r.floor === ownRoom?.floor : r.pool === pool);
  const rooms = data.rooms.filter(
    (r) => r.id === place?.room || r.id === initialRoom || (movable(r) && r.is_active && activeFloor.has(r.floor)),
  );
  const floors = data.floors.filter((f) => rooms.some((r) => r.floor === f.id));
  // A place assigned on its own may sit in a room the department admin does
  // not administer (not listed): keep it as it is.
  const unlistedRoom = place !== null && !rooms.some((r) => r.id === place.room);
  const features = data.features;

  const [room, setRoom] = useState<number | "">(place?.room ?? initialRoom ?? rooms[0]?.id ?? "");
  const [kind, setKind] = useState<PlaceKind>(place?.kind ?? initialKind ?? "desk");
  const [nameDe, setNameDe] = useState(place?.name_de || place?.name || initialName || "");
  const [nameEn, setNameEn] = useState(place?.name_en ?? "");
  const [capacity, setCapacity] = useState<number | "">(place?.capacity ?? initialCapacity ?? "");
  const [featureIds, setFeatureIds] = useState<number[]>(place?.features ?? []);
  // "Like the room": the place follows its room's groups (default when new).
  const [follows, setFollows] = useState(!(place?.groups_overridden ?? false));
  // Whether `groupIds` already holds the place's own set: from the start when
  // it was overridden on opening, else once seeded from the room. Kept while
  // "Like the room" is toggled back and forth.
  const [ownSeeded, setOwnSeeded] = useState(place?.groups_overridden ?? false);
  const [groupIds, setGroupIds] = useState<number[]>(place?.access_groups ?? []);
  const [special, setSpecial] = useState(place?.is_special ?? false);
  const [owner, setOwner] = useState<PersonChoice | null>(
    place?.fixed_owner ? { id: place.fixed_owner, name: place.fixed_owner_name ?? `#${place.fixed_owner}` } : null,
  );
  const [active, setActive] = useState(place?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const roomGroupIds = data.rooms.find((r) => r.id === room)?.access_groups ?? [];
  // A follower shows (and, when moved, takes) the chosen room's groups.
  const shownGroupIds = follows ? roomGroupIds : groupIds;

  const toggle = (list: number[], id: number) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  const meeting = kind === "meeting_room";
  // A fixed desk is never a special place (its statistics would reveal the
  // owner's absence days); the backend refuses the combination.
  const fixedDesk = !meeting && owner !== null;
  const valid = room !== "" && hasDefaultName(nameDe, nameEn) && (!meeting || Number(capacity) > 0);

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
          // A follower only states that; the server copies the room's groups.
          groups_overridden: !follows,
          access_groups: follows ? roomGroupIds : groupIds,
          is_special: special && !fixedDesk,
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
          {unlistedRoom && <option value={place.room}>{t("Current room")}</option>}
          {floors.map((f) => (
            <optgroup key={f.id} label={[f.building_code, f.name].filter(Boolean).join(" · ")}>
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

      <AccessGroupCheckboxes
        legend={t("Who may book")}
        hint={t("Without a group every member of the department may book this place. With groups only their members may book it, also people outside the pool.")}
        before={
          <label className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={follows}
              onChange={(e) => {
                setFollows(e.target.checked);
                // Deviating starts from the place's own set when it had one,
                // else (first time) from what the room gives now.
                if (!e.target.checked && !ownSeeded) {
                  setGroupIds(roomGroupIds);
                  setOwnSeeded(true);
                }
              }}
            />
            <span>{t("Like the room")}</span>
          </label>
        }
        groups={groups.data ?? null}
        selected={shownGroupIds}
        disabled={follows}
        onToggle={(id) => setGroupIds((l) => toggle(l, id))}
      />

      <label className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
        <input
          type="checkbox"
          className="h-5 w-5"
          checked={special && !fixedDesk}
          disabled={fixedDesk}
          onChange={(e) => setSpecial(e.target.checked)}
        />
        <span>
          {t("Special place")}
          <span className="block text-xs text-slate-600 dark:text-slate-300">
            {fixedDesk ? t("A fixed desk cannot be a special place.") : t("Reported individually in the statistics.")}
          </span>
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

      {error && <WarningNotice message={error} />}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !valid} className={primaryBtn}>{t("Save")}</button>
        <button type="button" onClick={onClose} className={secondaryBtn}>{t("Cancel")}</button>
      </div>
    </form>
  );
}
