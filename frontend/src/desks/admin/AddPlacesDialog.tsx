// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { BottomSheet } from "../../components/BottomSheet";
import { WarningNotice } from "../../components/WarningNotice";
import { desksApi } from "../api";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import type { BatchResult, PlaceKind, Room } from "../types";
import { BatchPreview, FieldError, errorOf, fieldErrors } from "./batchPreview";

/** Add places to rooms: a count per room, named after the campus pattern, with
 *  a preview (dry run) before anything is created. */
export function AddPlacesDialog({
  open,
  rooms,
  initialRoomIds,
  onClose,
  onCreated,
  onCustomName,
}: {
  open: boolean;
  /** The rooms places may be added to. */
  rooms: Room[];
  initialRoomIds: number[];
  onClose: () => void;
  onCreated: (count: number, skipped: number) => void;
  /** One place with an own name in this room (the single place form). */
  onCustomName: (roomId: number, kind: PlaceKind, capacity: number | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={t("Add places")} onClose={onClose}>
      {open && (
        <AddPlacesForm
          rooms={rooms}
          initialRoomIds={initialRoomIds}
          onClose={onClose}
          onCreated={onCreated}
          onCustomName={onCustomName}
        />
      )}
    </BottomSheet>
  );
}

function AddPlacesForm({
  rooms,
  initialRoomIds,
  onClose,
  onCreated,
  onCustomName,
}: {
  rooms: Room[];
  initialRoomIds: number[];
  onClose: () => void;
  onCreated: (count: number, skipped: number) => void;
  onCustomName: (roomId: number, kind: PlaceKind, capacity: number | null) => void;
}) {
  const { t } = useTranslation();
  const [roomIds, setRoomIds] = useState<number[]>(() => initialRoomIds.filter((id) => rooms.some((r) => r.id === id)));
  const [count, setCount] = useState<number | "">(1);
  const [kind, setKind] = useState<PlaceKind>("desk");
  const [capacity, setCapacity] = useState<number | "">("");
  const [preview, setPreview] = useState<{ key: string; result: BatchResult } | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const meeting = kind === "meeting_room";
  const key = JSON.stringify([roomIds, count, kind, meeting ? capacity : null]);
  const current = preview?.key === key ? preview.result : null;
  const valid =
    roomIds.length > 0 &&
    Number.isInteger(count) &&
    Number(count) >= 1 &&
    Number(count) <= 50 &&
    (!meeting || Number(capacity) >= 1);
  const body = {
    // Keep the floor's order, not the order of clicking.
    room_ids: rooms.filter((r) => roomIds.includes(r.id)).map((r) => r.id),
    count: Number(count),
    kind,
    ...(meeting ? { capacity: Number(capacity) } : {}),
  };

  const toggle = (id: number) => setRoomIds((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]));

  async function run(dry: boolean) {
    if (busy) return;
    setBusy(true);
    setFields({});
    setGeneral(null);
    try {
      const result = await desksApi.batchPlaces({ ...body, dry_run: dry });
      if (dry) setPreview({ key, result });
      else onCreated(result.created.length, result.skipped.length);
    } catch (e) {
      if (dry) setPreview(null);
      const { fields: f, general: g } = fieldErrors(e);
      setFields(f);
      setGeneral(g);
    }
    setBusy(false);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && current && current.created.length > 0) void run(false);
      }}
      className="flex flex-col gap-4"
    >
      <fieldset>
        <legend className={labelCls}>{t("Rooms")}</legend>
        {rooms.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">{t("This floor has no rooms yet.")}</p>
        ) : (
          <div className="flex max-h-48 flex-col overflow-y-auto">
            {rooms.map((r) => (
              <label key={r.id} className="flex min-h-[44px] items-center gap-3 text-sm text-slate-800 dark:text-slate-200">
                <input type="checkbox" className="h-5 w-5" checked={roomIds.includes(r.id)} onChange={() => toggle(r.id)} />
                {r.name}
              </label>
            ))}
          </div>
        )}
        <FieldError id="places-rooms-error" message={errorOf(fields, "room_ids")} />
      </fieldset>
      <div>
        <label htmlFor="places-count" className={labelCls}>{t("Places per room")}</label>
        <input
          id="places-count"
          type="number"
          min={1}
          max={50}
          value={count}
          onChange={(e) => setCount(e.target.value === "" ? "" : Number(e.target.value))}
          aria-describedby="places-count-error"
          className={inputCls}
        />
        <FieldError id="places-count-error" message={errorOf(fields, "count")} />
      </div>
      <SegmentedControl
        size="md"
        ariaLabel={t("Kind")}
        value={kind}
        onChange={setKind}
        options={[
          { value: "desk" as const, label: t("Desk") },
          { value: "meeting_room" as const, label: t("Meeting room") },
        ]}
        className="w-full sm:w-max"
      />
      <FieldError id="places-kind-error" message={errorOf(fields, "kind")} />
      {meeting && (
        <div>
          <label htmlFor="places-capacity" className={labelCls}>{t("Capacity (persons)")}</label>
          <input
            id="places-capacity"
            type="number"
            min={1}
            required
            value={capacity}
            onChange={(e) => setCapacity(e.target.value === "" ? "" : Number(e.target.value))}
            aria-describedby="places-capacity-error"
            className={inputCls}
          />
          <FieldError id="places-capacity-error" message={errorOf(fields, "capacity")} />
        </div>
      )}
      <FieldError id="places-dry-run-error" message={errorOf(fields, "dry_run")} />
      {current && <BatchPreview result={current} />}
      {general && <WarningNotice message={general} />}
      {roomIds.length === 1 && (
        <button type="button" onClick={() => onCustomName(roomIds[0], kind, meeting && capacity !== "" ? Number(capacity) : null)} className="min-h-[44px] self-start text-sm font-semibold text-slate-800 underline underline-offset-2 dark:text-slate-200">
          {t("Single place with its own name")}
        </button>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void run(true)} disabled={busy || !valid} className={secondaryBtn}>
          {t("Preview")}
        </button>
        <button
          type="submit"
          disabled={busy || !valid || !(current && current.created.length > 0)}
          className={primaryBtn}
        >
          {t("Create")}
        </button>
        <button type="button" onClick={onClose} className={secondaryBtn}>{t("Cancel")}</button>
      </div>
    </form>
  );
}
