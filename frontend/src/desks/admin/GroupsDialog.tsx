// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AccessGroupPicker } from "../../components/AccessGroupPicker";
import { BottomSheet } from "../../components/BottomSheet";
import { WarningNotice } from "../../components/WarningNotice";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { primaryBtn, secondaryBtn } from "../components/formStyles";
import { fieldErrors } from "./batchPreview";

/**
 * Add and remove the access groups ("Who may book") of the selected rooms
 * (their following places) and places in one go: one list of the groups the
 * selection has now ("2 of 5" when only some have it); ✕ removes a group from
 * all, "Add group" adds one to all. The group list is the one of
 * `pool`, the first assigned department of the selection: every ordinary group
 * is offered whatever the department, only the "in the pool" hint differs.
 */
export function GroupsDialog({
  open,
  pool,
  roomIds,
  placeIds,
  current,
  onClose,
  onDone,
}: {
  open: boolean;
  /** Department whose group list is offered. */
  pool: number;
  roomIds: number[];
  placeIds: number[];
  /** Current groups of each selected room and place. */
  current: number[][];
  onClose: () => void;
  onDone: (placesChanged: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={t("Access groups")} onClose={onClose}>
      {open && (
        <GroupsForm
          pool={pool}
          roomIds={roomIds}
          placeIds={placeIds}
          current={current}
          onClose={onClose}
          onDone={onDone}
        />
      )}
    </BottomSheet>
  );
}

function GroupsForm({
  pool,
  roomIds,
  placeIds,
  current,
  onClose,
  onDone,
}: {
  pool: number;
  roomIds: number[];
  placeIds: number[];
  current: number[][];
  onClose: () => void;
  onDone: (placesChanged: number) => void;
}) {
  const { t } = useTranslation();
  const groups = useFetch(() => desksApi.accessGroups(pool), [pool]);
  const list = groups.data ?? null;
  const [addIds, setAddIds] = useState<number[]>([]);
  const [removeIds, setRemoveIds] = useState<number[]>([]);
  const [follow, setFollow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // How many of the selected rooms/places have each group now.
  const counts = new Map<number, number>();
  for (const ids of current) for (const id of new Set(ids)) counts.set(id, (counts.get(id) ?? 0) + 1);
  const shown = [
    ...[...counts.keys()].filter((id) => !removeIds.includes(id)),
    ...addIds.filter((id) => !counts.has(id)),
  ];
  const total = current.length;
  // Groups only some of the selection have: can still be added to all.
  const partial = [...counts.keys()].filter(
    (id) => (counts.get(id) ?? 0) < total && !addIds.includes(id) && !removeIds.includes(id),
  );
  function removeShown(id: number) {
    // ✕: drop a pending addition; a group the selection has goes from all.
    setAddIds((l) => l.filter((x) => x !== id));
    if (counts.has(id)) setRemoveIds((l) => (l.includes(id) ? l : [...l, id]));
  }
  function addToAll(id: number) {
    setRemoveIds((l) => l.filter((x) => x !== id));
    if ((counts.get(id) ?? 0) < total) setAddIds((l) => (l.includes(id) ? l : [...l, id]));
  }
  // Following the room again ignores add/remove for places (server rule);
  // with rooms selected too, add/remove still changes the rooms.
  const pickersOff = follow && roomIds.length === 0;
  const ready = (!pickersOff && addIds.length + removeIds.length > 0) || follow;

  async function submit() {
    if (busy || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const { places_changed } = await desksApi.applyPlaceGroups({
        room_ids: roomIds,
        place_ids: placeIds,
        add_ids: pickersOff ? [] : addIds,
        remove_ids: pickersOff ? [] : removeIds,
        follow_room: follow,
      });
      onDone(places_changed);
    } catch (e) {
      const { fields, general } = fieldErrors(e);
      setError(
        [general, ...Object.values(fields).flat()].filter(Boolean).join(" ") ||
          t("The request failed."),
      );
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-4"
    >
      <p className="text-sm text-slate-700 dark:text-slate-200">
        {roomIds.length > 0
          ? t(
              "Rooms pass their groups on to their places that follow them; places with their own groups keep those until changed here.",
            )
          : t(
              "Without a group every member of the department may book a place. With groups only their members may book it, also people outside the pool.",
            )}
      </p>
      {groups.error && <WarningNotice message={groups.error} />}
      {!pickersOff && (
        <>
          <AccessGroupPicker
            legend={t("Who may book")}
            groups={list}
            selected={shown}
            onToggle={removeShown}
            onAdd={addToAll}
            alsoAddable={partial}
            note={(id) => {
              const n = counts.get(id) ?? 0;
              return total > 1 && !addIds.includes(id) && n < total
                ? t("{{count}} of {{total}}", { count: n, total })
                : undefined;
            }}
          />
        </>
      )}
      {placeIds.length > 0 && (
        <label className="flex min-h-[44px] items-start gap-3 text-sm text-slate-800 dark:text-slate-200">
          <input
            type="checkbox"
            className="mt-0.5 h-5 w-5"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
          />
          <span>
            {t("Places follow their room again")}
            <span className="block text-xs text-slate-600 dark:text-slate-300">
              {t(
                "The selected places drop their own groups and take their room's groups.",
              )}
              {roomIds.length > 0 &&
                ` ${t("Adding and removing then applies to the rooms only.")}`}
            </span>
          </span>
        </label>
      )}
      <p className="text-sm text-slate-700 dark:text-slate-200">
        {t("Removing groups can end bookings of people who lose access.")}
      </p>
      {error && <WarningNotice message={error} />}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !ready} className={primaryBtn}>
          {t("Apply")}
        </button>
        <button type="button" onClick={onClose} className={secondaryBtn}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
