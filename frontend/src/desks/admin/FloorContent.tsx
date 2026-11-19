// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DoorOpen, LampDesk, Map as MapIcon, PencilRuler, Plus } from "lucide-react";
import { ApiError } from "../../api";
import { useAuth } from "../../auth";
import { BottomSheet } from "../../components/BottomSheet";
import { useConfirm } from "../../components/ConfirmDialog";
import { KebabMenu, type KebabItem } from "../../components/KebabMenu";
import { Empty } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { WarningNotice } from "../../components/WarningNotice";
import { desksApi } from "../api";
import type { PlacesAdminData } from "../components/adminTypes";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import { NameField, hasDefaultName } from "../components/NameField";
import { PlaceFormDialog } from "../components/PlaceFormDialog";
import type { Floor, Place, PlaceInput, PlaceKind, Room, RoomKind } from "../types";
import { AddPlacesDialog } from "./AddPlacesDialog";
import { AddRoomsDialog } from "./AddRoomsDialog";
import { RoomRow } from "./RoomRow";

const byName = (a: { name: string }, b: { name: string }) =>
  a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });

/** Selected rooms and places (app admins; for the department assignment). */
export interface Selection {
  roomIds: Set<number>;
  placeIds: Set<number>;
  setRoomIds: (update: (ids: Set<number>) => Set<number>) => void;
  setPlaceIds: (update: (ids: Set<number>) => Set<number>) => void;
}

/** `ids` with `id` added or removed. */
function toggled(ids: Set<number>, id: number, on = !ids.has(id)): Set<number> {
  const next = new Set(ids);
  if (on) next.add(id);
  else next.delete(id);
  return next;
}

const errorText = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

/** After a delete (same answer either way): is the row still there ("kept",
 *  only deactivated), gone ("deleted", 404), or is that unknown (any other
 *  failure of the look-up)? */
function probeDeleted(fetchRow: () => Promise<unknown>): Promise<"kept" | "deleted" | "unknown"> {
  return fetchRow().then(
    () => "kept",
    (e: unknown) => (e instanceof ApiError && e.status === 404 ? "deleted" : "unknown"),
  );
}

/**
 * The chosen floor: its plan card, then its rooms (naturally sorted) with
 * their places. App admins see and edit everything; department admins the
 * rooms of the current department (or holding its places) and edit the rooms
 * and places of the departments they administer.
 */
export function FloorContent({
  floor,
  data,
  pool,
  appAdmin,
  names,
  departmentChoices,
  selection,
  onChanged,
}: {
  floor: Floor;
  data: PlacesAdminData;
  /** The current department. */
  pool: number;
  appAdmin: boolean;
  /** Department names by pool id (for the badges). */
  names: Map<number, string>;
  /** Active departments by pool id (the department of new rooms). */
  departmentChoices: Map<number, string>;
  selection: Selection;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const { user } = useAuth();
  const adminPools = new Set(user?.desk_admin_pool_ids ?? []);
  const mayAdmin = (id: number | null) => appAdmin || (id !== null && adminPools.has(id));

  const [editingRoom, setEditingRoom] = useState<Room | null>(null);
  const [roomError, setRoomError] = useState<string | null>(null);
  const [editingPlace, setEditingPlace] = useState<Place | null>(null);
  const [placeError, setPlaceError] = useState<string | null>(null);
  const [adding, setAdding] = useState<"rooms" | "places" | null>(null);
  // Expanded rooms per floor (collapsed by default; kept while switching floors).
  const [expandedByFloor, setExpandedByFloor] = useState<Map<number, Set<number>>>(() => new Map());
  const expanded = expandedByFloor.get(floor.id) ?? new Set<number>();
  const setExpanded = (ids: Set<number>) => setExpandedByFloor((m) => new Map(m).set(floor.id, ids));
  const [newPlace, setNewPlace] = useState<{ room: number; name: string; kind: PlaceKind; capacity: number | null } | null>(null);

  // Department admins: rooms of the current department or holding its places.
  const ownRooms = new Set(data.places.filter((p) => p.pool === pool).map((p) => p.room));
  const rooms = data.rooms
    .filter((r) => r.floor === floor.id && (appAdmin || r.pool === pool || ownRooms.has(r.id)))
    .sort(byName);
  const placesOf = (roomId: number) => data.places.filter((p) => p.room === roomId).sort(byName);
  const allExpanded = rooms.length > 0 && rooms.every((r) => expanded.has(r.id));

  // Rooms places may be added to: active ones the user administers.
  const addableRooms = data.rooms.filter((r) => r.floor === floor.id && r.is_active && mayAdmin(r.pool)).sort(byName);
  const addItems: KebabItem[] = [
    ...(appAdmin ? [{ label: t("Add rooms"), icon: DoorOpen, onClick: () => setAdding("rooms") }] : []),
    ...(addableRooms.length > 0 ? [{ label: t("Add places"), icon: LampDesk, onClick: () => setAdding("places") }] : []),
  ];
  const preselected = addableRooms.filter((r) => selection.roomIds.has(r.id)).map((r) => r.id);
  const initialRoomIds = preselected.length > 0 ? preselected : addableRooms.length === 1 ? [addableRooms[0].id] : [];

  async function startCustomPlace(roomId: number, kind: PlaceKind, capacity: number | null) {
    try {
      const { names } = await desksApi.nameSuggestions(roomId, 1);
      setAdding(null);
      setPlaceError(null);
      setNewPlace({ room: roomId, name: names[0] ?? "", kind, capacity });
    } catch (e) {
      toast.error(errorText(e, t("The request failed.")));
    }
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
    if (!ok) return;
    try {
      await desksApi.deleteRoom(r.id);
      // The answer is the same either way: look whether the room is still there.
      const outcome = await probeDeleted(() => desksApi.room(r.id));
      toast.success(
        outcome === "kept"
          ? t("Room deactivated: it has a booking history. Its places were retired and upcoming bookings cancelled.")
          : outcome === "deleted"
            ? t("Room deleted.")
            : t("Deleted."),
      );
      selection.setRoomIds((ids) => toggled(ids, r.id, false));
      const placeIds = data.places.filter((p) => p.room === r.id).map((p) => p.id);
      selection.setPlaceIds((ids) => new Set([...ids].filter((id) => !placeIds.includes(id))));
      onChanged();
    } catch (e) {
      toast.error(errorText(e, t("The request failed.")));
    }
  }

  async function removePlace(p: Place) {
    const ok = await confirm({
      title: t("Delete place"),
      message: t(
        "Delete {{name}}? Without reservation history it is removed for good; otherwise it is only retired (kept for the history) and upcoming reservations are cancelled and their holders informed.",
        { name: p.name },
      ),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deletePlace(p.id);
      const outcome = await probeDeleted(() => desksApi.place(p.id));
      toast.success(
        outcome === "kept"
          ? t("Place retired: it has a booking history. Upcoming bookings were cancelled and their holders informed.")
          : outcome === "deleted"
            ? t("Place deleted.")
            : t("Deleted."),
      );
      selection.setPlaceIds((ids) => toggled(ids, p.id, false));
      onChanged();
    } catch (e) {
      toast.error(errorText(e, t("The request failed.")));
    }
  }

  async function regenerateQr(p: Place) {
    const ok = await confirm({
      title: t("Regenerate QR code"),
      message: t("Regenerate the QR code of {{name}}? The printed sticker stops working and must be replaced.", {
        name: p.name,
      }),
      confirmLabel: t("Regenerate"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.regeneratePlaceQr(p.id);
      toast.success(t("QR code regenerated."));
      onChanged();
    } catch (e) {
      toast.error(errorText(e, t("The request failed.")));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PlanCard floor={floor} data={data} appAdmin={appAdmin} />
      <section aria-labelledby="floor-rooms-title" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="floor-rooms-title" className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {t("Rooms")}
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            {rooms.length > 0 && (
              <button
                type="button"
                onClick={() => setExpanded(allExpanded ? new Set() : new Set(rooms.map((r) => r.id)))}
                className={secondaryBtn}
              >
                {allExpanded ? t("Collapse all") : t("Expand all")}
              </button>
            )}
            {addItems.length > 0 && (
              <KebabMenu items={addItems} trigger={{ label: t("Add"), glyph: "+", chevron: true, className: secondaryBtn }} />
            )}
          </div>
        </div>
        {rooms.length === 0 ? (
          <Empty icon={DoorOpen} label={t("This floor has no rooms yet.")} />
        ) : (
          <ul className="flex flex-col gap-3">
            {rooms.map((r) => (
              <RoomRow
                key={r.id}
                room={r}
                places={placesOf(r.id)}
                names={names}
                appAdmin={appAdmin}
                expanded={expanded.has(r.id)}
                onToggleExpanded={() => setExpanded(toggled(expanded, r.id))}
                canEditRoom={mayAdmin(r.pool)}
                canEditPlace={(p) => mayAdmin(p.pool)}
                roomSelected={selection.roomIds.has(r.id)}
                selectedPlaceIds={selection.placeIds}
                onToggleRoom={() => selection.setRoomIds((ids) => toggled(ids, r.id))}
                onTogglePlace={(p) => selection.setPlaceIds((ids) => toggled(ids, p.id))}
                onEditRoom={() => {
                  setRoomError(null);
                  setEditingRoom(r);
                }}
                onDeleteRoom={() => removeRoom(r)}
                onEditPlace={(p) => {
                  setPlaceError(null);
                  setEditingPlace(p);
                }}
                onDeletePlace={removePlace}
                onRegenerateQr={regenerateQr}
              />
            ))}
          </ul>
        )}
      </section>

      <BottomSheet open={editingRoom !== null} title={t("Edit room")} onClose={() => setEditingRoom(null)}>
        {editingRoom && (
          <RoomForm
            key={editingRoom.id}
            room={editingRoom}
            error={roomError}
            onCancel={() => setEditingRoom(null)}
            onSave={async (v) => {
              try {
                await desksApi.updateRoom(editingRoom.id, v);
                toast.success(t("Room saved."));
                setEditingRoom(null);
                onChanged();
              } catch (e) {
                setRoomError(errorText(e, t("The request failed.")));
              }
            }}
          />
        )}
      </BottomSheet>
      <AddRoomsDialog
        open={adding === "rooms"}
        floor={floor}
        pools={departmentChoices}
        onClose={() => setAdding(null)}
        onCreated={(count, skipped) => {
          setAdding(null);
          toast.success(t("{{count}} rooms created, {{skipped}} skipped", { count, skipped }));
          onChanged();
        }}
      />
      <AddPlacesDialog
        open={adding === "places"}
        rooms={addableRooms}
        initialRoomIds={initialRoomIds}
        onClose={() => setAdding(null)}
        onCreated={(count, skipped, roomIds) => {
          setAdding(null);
          // Show the new places: open the rooms they were added to.
          setExpanded(new Set([...expanded, ...roomIds]));
          toast.success(t("{{count}} places created, {{skipped}} skipped", { count, skipped }));
          onChanged();
        }}
        onCustomName={startCustomPlace}
      />
      <PlaceFormDialog
        open={newPlace !== null}
        pool={data.rooms.find((r) => r.id === newPlace?.room)?.pool ?? pool}
        data={data}
        place={null}
        initialRoom={newPlace?.room}
        initialName={newPlace?.name}
        initialKind={newPlace?.kind}
        initialCapacity={newPlace?.capacity}
        error={placeError}
        onClose={() => setNewPlace(null)}
        onSave={async (input: PlaceInput) => {
          try {
            await desksApi.createPlace(input);
            if (newPlace) setExpanded(new Set([...expanded, newPlace.room]));
            toast.success(t("Place saved."));
            setNewPlace(null);
            onChanged();
            return true;
          } catch (e) {
            setPlaceError(errorText(e, t("The request failed.")));
            return false;
          }
        }}
      />
      <PlaceFormDialog
        open={editingPlace !== null}
        // The place's own department (access groups, people, rooms); an
        // unassigned place falls back on the current one.
        pool={editingPlace?.pool ?? pool}
        data={data}
        place={editingPlace}
        error={placeError}
        onClose={() => setEditingPlace(null)}
        onSave={async (input: PlaceInput) => {
          if (!editingPlace) return false;
          try {
            await desksApi.updatePlace(editingPlace.id, input);
            toast.success(t("Place saved."));
            setEditingPlace(null);
            onChanged();
            return true;
          } catch (e) {
            setPlaceError(errorText(e, t("The request failed.")));
            return false;
          }
        }}
      />
    </div>
  );
}

/** The floor's plan: what is done so far and the way into the editor. */
function PlanCard({ floor, data, appAdmin }: { floor: Floor; data: PlacesAdminData; appAdmin: boolean }) {
  const { t } = useTranslation();
  const roomIds = new Set(data.rooms.filter((r) => r.floor === floor.id).map((r) => r.id));
  const floorPlaces = data.places.filter((p) => roomIds.has(p.room));
  const placed = floorPlaces.filter((p) => p.plan_symbol).length;
  const drawn = (floor.plan?.shapes?.length ?? 0) > 0;
  const facts = [
    drawn ? t("Plan drawn") : t("No plan yet"),
    t("{{placed}} of {{total}} places on the plan", { placed, total: floorPlaces.length }),
    floor.has_template ? t("Template uploaded") : null,
    floor.scale_px_per_m ? t("Scale set") : null,
  ].filter(Boolean);
  const to = `/desks/manage/plans/${floor.id}`;
  return (
    <section
      aria-labelledby="floor-plan-title"
      className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center dark:border-slate-700"
    >
      <MapIcon aria-hidden className="hidden h-6 w-6 shrink-0 text-slate-500 sm:block dark:text-slate-400" />
      <div className="min-w-0 flex-1">
        <h2 id="floor-plan-title" className="font-semibold text-slate-900 dark:text-slate-100">
          {t("Floor plan")}
        </h2>
        <p className="text-xs text-slate-600 dark:text-slate-300">{facts.join(" · ")}</p>
      </div>
      {drawn ? (
        <Link to={to} className={secondaryBtn}>
          <PencilRuler aria-hidden className="h-4 w-4" />
          {t("Edit plan")}
        </Link>
      ) : (
        appAdmin && (
          <Link to={to} className={secondaryBtn}>
            <Plus aria-hidden className="h-4 w-4" />
            {t("Create plan")}
          </Link>
        )
      )}
    </section>
  );
}

function RoomForm({
  room,
  error,
  onSave,
  onCancel,
}: {
  room: Room;
  error: string | null;
  onSave: (v: { name_de: string; name_en: string | null; kind: RoomKind; is_active: boolean }) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [nameDe, setNameDe] = useState(room.name_de ?? "");
  const [nameEn, setNameEn] = useState(room.name_en ?? "");
  const [kind, setKind] = useState<RoomKind>(room.kind);
  const [active, setActive] = useState(room.is_active);
  const kindId = useId();
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
        <label htmlFor={kindId} className={labelCls}>
          {t("Kind")}
        </label>
        <select id={kindId} value={kind} onChange={(e) => setKind(e.target.value as RoomKind)} className={inputCls}>
          <option value="office">{t("Office")}</option>
          <option value="meeting">{t("Meeting room area")}</option>
        </select>
      </div>
      <label className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
        <input type="checkbox" className="h-5 w-5" checked={active} onChange={(e) => setActive(e.target.checked)} />
        <span>
          {t("Active (bookable)")}
          {room.is_active && !active && (
            <span className="block text-xs text-slate-600 dark:text-slate-300">
              {t("Deactivating retires the room's places and cancels their upcoming bookings.")}
            </span>
          )}
        </span>
      </label>
      {error && <WarningNotice message={error} />}
      <div className="flex flex-wrap gap-2">
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
