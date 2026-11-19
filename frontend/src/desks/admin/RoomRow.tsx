// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Pencil, RefreshCw, Trash2, Building2, Unlink, Users } from "lucide-react";
import { KebabMenu, type KebabItem } from "../../components/KebabMenu";
import type { Place, Room } from "../types";
import { DepartmentBadge } from "./DepartmentBadge";
import { actionsTrigger } from "./LocationBar";

const checkboxLabelCls = "flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center";
const selectedCls = "bg-brand-50 dark:bg-brand-500/10";

/**
 * One room of the floor with its places nested below: name, kind, number of
 * places, department badges and the actions the viewer may take. The header
 * toggles the places (collapsed by default); checkbox and actions sit beside
 * the toggle. App admins get a checkbox per room and place (for the
 * department assignment); a selected room marks the places that follow it
 * (all but the deliberately different ones).
 */
export function RoomRow({
  room,
  places,
  names,
  appAdmin,
  expanded,
  onToggleExpanded,
  canEditRoom,
  canEditPlace,
  roomSelected,
  selectedPlaceIds,
  onToggleRoom,
  onTogglePlace,
  onEditRoom,
  onDeleteRoom,
  onEditPlace,
  onDeletePlace,
  onRegenerateQr,
  onGroups,
  onAssign,
}: {
  room: Room;
  /** The room's places, already sorted. */
  places: Place[];
  names: Map<number, string>;
  appAdmin: boolean;
  /** Places shown below the room. */
  expanded: boolean;
  onToggleExpanded: () => void;
  canEditRoom: boolean;
  canEditPlace: (place: Place) => boolean;
  roomSelected: boolean;
  selectedPlaceIds: Set<number>;
  onToggleRoom: () => void;
  onTogglePlace: (place: Place) => void;
  onEditRoom: () => void;
  onDeleteRoom: () => void;
  onEditPlace: (place: Place) => void;
  onDeletePlace: (place: Place) => void;
  onRegenerateQr: (place: Place) => void;
  /** Access groups of one room / place ("Zugriffsgruppen…"). */
  onGroups: (target: { roomIds: number[]; placeIds: number[] }) => void;
  /** Assign / remove the department of one room / place (app admins). */
  onAssign: (target: { roomIds: number[]; placeIds: number[] }, unassign: boolean) => void;
}) {
  const { t } = useTranslation();
  const mixed = new Set(places.map((p) => p.pool)).size > 1;
  const roomActions: KebabItem[] = [
    ...(canEditRoom
      ? [
          { label: t("Edit room"), icon: Pencil, onClick: onEditRoom },
          { label: t("Access groups…"), icon: Users, onClick: () => onGroups({ roomIds: [room.id], placeIds: [] }) },
        ]
      : []),
    ...(appAdmin
      ? [
          { label: t("Assign department…"), icon: Building2, onClick: () => onAssign({ roomIds: [room.id], placeIds: [] }, false) },
          ...(room.pool !== null
            ? [{ label: t("Remove assignment"), icon: Unlink, onClick: () => onAssign({ roomIds: [room.id], placeIds: [] }, true) }]
            : []),
        ]
      : []),
    ...(appAdmin ? [{ label: t("Delete room"), icon: Trash2, onClick: onDeleteRoom, danger: true }] : []),
  ];
  const listId = `room-${room.id}-places`;
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <li className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <div className={`flex items-center gap-2 px-2 py-1 ${roomSelected ? selectedCls : ""}`}>
        {appAdmin && (
          <label className={checkboxLabelCls}>
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={roomSelected}
              onChange={onToggleRoom}
              aria-label={t("Select room {{name}}", { name: room.name })}
            />
          </label>
        )}
        <button
          type="button"
          onClick={onToggleExpanded}
          aria-expanded={expanded}
          aria-controls={expanded ? listId : undefined}
          title={expanded ? t("Hide places") : t("Show places")}
          className={`flex min-h-[44px] min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 ${appAdmin ? "" : "pl-2"}`}
        >
          <span className="flex min-w-0 flex-1 basis-40 items-center gap-2">
            <Chevron aria-hidden className="h-4 w-4 shrink-0 text-slate-600 dark:text-slate-300" />
            <span className="min-w-0">
              <span className="block font-semibold text-slate-900 dark:text-slate-100">{room.name}</span>
              <span className="block text-xs text-slate-600 dark:text-slate-300">
                {room.kind === "meeting" ? t("Meeting room area") : t("Office")}
                {` · ${t("{{count}} places", { count: places.length })}`}
                {room.is_active ? "" : ` · ${t("Inactive")}`}
              </span>
            </span>
          </span>
          <DepartmentBadge pool={room.pool} names={names} note={mixed ? "mixed" : undefined} />
        </button>
        {roomActions.length > 0 ? (
          <KebabMenu items={roomActions} label={t("Actions for room {{name}}", { name: room.name })} trigger={actionsTrigger} />
        ) : (
          <span aria-hidden className="w-11 shrink-0" />
        )}
      </div>
      {!expanded ? null : places.length === 0 ? (
        <p id={listId} className="border-t border-slate-200 px-4 py-2 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-300">
          {t("No places in this room yet.")}
        </p>
      ) : (
        <ul id={listId} className="divide-y divide-slate-200 border-t border-slate-200 dark:divide-slate-700 dark:border-slate-700">
          {places.map((p) => (
            <PlaceRow
              key={p.id}
              place={p}
              names={names}
              appAdmin={appAdmin}
              canEdit={canEditPlace(p)}
              selected={selectedPlaceIds.has(p.id)}
              // Selecting the room reaches the places that follow it.
              marked={selectedPlaceIds.has(p.id) || (roomSelected && !p.pool_overridden)}
              onToggle={() => onTogglePlace(p)}
              onEdit={() => onEditPlace(p)}
              onDelete={() => onDeletePlace(p)}
              onRegenerateQr={() => onRegenerateQr(p)}
              onGroups={() => onGroups({ roomIds: [], placeIds: [p.id] })}
              onAssign={(unassign) => onAssign({ roomIds: [], placeIds: [p.id] }, unassign)}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function PlaceRow({
  place,
  names,
  appAdmin,
  canEdit,
  selected,
  marked,
  onToggle,
  onEdit,
  onDelete,
  onRegenerateQr,
  onGroups,
  onAssign,
}: {
  place: Place;
  names: Map<number, string>;
  appAdmin: boolean;
  canEdit: boolean;
  selected: boolean;
  marked: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onRegenerateQr: () => void;
  onGroups: () => void;
  onAssign: (unassign: boolean) => void;
}) {
  const { t } = useTranslation();
  const facts = [
    place.kind === "meeting_room" ? t("Meeting room, {{n}} persons", { n: place.capacity ?? 0 }) : t("Desk"),
    place.is_special ? t("Special place") : null,
    place.fixed_owner ? t("Fixed owner: {{name}}", { name: place.fixed_owner_name ?? "" }) : null,
    place.is_active ? null : t("Inactive"),
  ].filter(Boolean);
  const actions: KebabItem[] = canEdit
    ? [
        { label: t("Edit place"), icon: Pencil, onClick: onEdit },
        { label: t("Access groups…"), icon: Users, onClick: onGroups },
        ...(appAdmin
          ? [
              { label: t("Assign department…"), icon: Building2, onClick: () => onAssign(false) },
              ...(place.pool !== null ? [{ label: t("Remove assignment"), icon: Unlink, onClick: () => onAssign(true) }] : []),
            ]
          : []),
        { label: t("Regenerate QR code"), icon: RefreshCw, onClick: onRegenerateQr },
        { label: t("Delete place"), icon: Trash2, onClick: onDelete, danger: true },
      ]
    : [];
  return (
    <li className={`flex items-center gap-2 py-1 pl-6 pr-2 ${marked ? selectedCls : ""}`}>
      {appAdmin && (
        <label className={checkboxLabelCls}>
          <input
            type="checkbox"
            className="h-5 w-5"
            checked={selected}
            onChange={onToggle}
            aria-label={t("Select place {{name}}", { name: place.name })}
          />
        </label>
      )}
      <div className={`flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 py-1.5 ${appAdmin ? "" : "pl-2"}`}>
        <div className="min-w-0 flex-1 basis-40">
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{place.name}</p>
          <p className="text-xs text-slate-600 dark:text-slate-300">{facts.join(" · ")}</p>
        </div>
        <DepartmentBadge pool={place.pool} names={names} note={place.pool_overridden ? "overridden" : undefined} />
      </div>
      {actions.length > 0 ? (
        <KebabMenu items={actions} label={t("Actions for place {{name}}", { name: place.name })} trigger={actionsTrigger} />
      ) : (
        <span aria-hidden className="w-11 shrink-0" />
      )}
    </li>
  );
}
