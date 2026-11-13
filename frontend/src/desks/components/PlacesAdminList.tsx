// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Pencil, Plus, QrCode, RefreshCw, Trash2 } from "lucide-react";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Place, PlaceInput } from "../types";
import type { AdminSectionProps } from "./adminTypes";
import { PlaceFormDialog } from "./PlaceFormDialog";
import { dangerBtn, secondaryBtn, sectionTitleCls } from "./formStyles";

const iconBtn =
  "flex h-11 w-11 items-center justify-center rounded-full hover:bg-slate-100 dark:hover:bg-slate-800";

/** The department's places: create, edit, delete (soft when it has a
 *  history), QR label and QR regeneration. */
export function PlacesAdminList({ pool, data, onChanged }: AdminSectionProps) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = useState<{ place: Place | null } | null>(null);

  const floorOfRoom = new Map(data.rooms.map((r) => [r.id, data.floors.find((f) => f.id === r.floor)]));
  const roomName = new Map(data.rooms.map((r) => [r.id, r.name]));
  const featureName = new Map(data.features.map((f) => [f.id, f.name]));
  const places = data.places
    .filter((p) => floorOfRoom.get(p.room)?.pool === pool)
    .sort(
      (a, b) =>
        (floorOfRoom.get(a.room)?.name ?? "").localeCompare(floorOfRoom.get(b.room)?.name ?? "") ||
        (roomName.get(a.room) ?? "").localeCompare(roomName.get(b.room) ?? "") ||
        a.name.localeCompare(b.name),
    );

  async function attempt(job: () => Promise<unknown>, done: string): Promise<boolean> {
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

  async function remove(p: Place) {
    const ok = await confirm({
      title: t("Delete place"),
      message: t(
        "Delete {{name}}? Without reservation history it is removed for good; otherwise it is only retired (kept for the history) and upcoming reservations are cancelled and their holders informed.",
        { name: p.name },
      ),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (ok) await attempt(() => desksApi.deletePlace(p.id), t("Place deleted."));
  }

  async function regenerate(p: Place) {
    const ok = await confirm({
      title: t("Regenerate QR code"),
      message: t(
        "Regenerate the QR code of {{name}}? The printed sticker stops working and must be replaced.",
        { name: p.name },
      ),
      confirmLabel: t("Regenerate"),
      danger: true,
    });
    if (ok) await attempt(() => desksApi.regeneratePlaceQr(p.id), t("QR code regenerated."));
  }

  return (
    <section aria-labelledby="places-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="places-title" className={sectionTitleCls}>
          {t("Places")}
        </h2>
        <div className="flex flex-wrap gap-2">
          <Link to="/desks/manage/qr" className={secondaryBtn}>
            <QrCode aria-hidden className="h-4 w-4" />
            {t("Print QR labels")}
          </Link>
          <button type="button" className={secondaryBtn} disabled={data.rooms.length === 0} onClick={() => setEditing({ place: null })}>
            <Plus aria-hidden className="h-4 w-4" />
            {t("Add place")}
          </button>
        </div>
      </div>
      {places.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {data.rooms.length === 0
            ? t("Add a floor and a room first.")
            : t("This department has no places yet.")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {places.map((p) => {
            const floor = floorOfRoom.get(p.room);
            const facts = [
              [floor?.building, floor?.name, roomName.get(p.room)].filter(Boolean).join(" · "),
              p.kind === "meeting_room" ? t("Meeting room, {{n}} persons", { n: p.capacity ?? 0 }) : t("Desk"),
              p.features.length ? p.features.map((id) => featureName.get(id) ?? "").filter(Boolean).join(", ") : null,
              p.is_special ? t("Special place") : null,
              p.access_groups.length ? t("{{count}} restriction group", { count: p.access_groups.length }) : null,
              p.fixed_owner ? t("Fixed owner: {{name}}", { name: p.fixed_owner_name ?? "" }) : null,
              p.is_active ? null : t("Inactive"),
            ].filter(Boolean);
            return (
              <li key={p.id} className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-center dark:border-slate-700">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-900 dark:text-slate-100">{p.name}</p>
                  <p className="text-xs text-slate-600 dark:text-slate-300">{facts.join(" · ")}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Link to={`/desks/manage/qr?place=${p.id}`} aria-label={t("QR label of {{name}}", { name: p.name })} className={iconBtn}>
                    <QrCode aria-hidden className="h-4 w-4" />
                  </Link>
                  <button type="button" aria-label={t("Regenerate QR code of {{name}}", { name: p.name })} className={iconBtn} onClick={() => regenerate(p)}>
                    <RefreshCw aria-hidden className="h-4 w-4" />
                  </button>
                  <button type="button" aria-label={t("Edit place {{name}}", { name: p.name })} className={iconBtn} onClick={() => setEditing({ place: p })}>
                    <Pencil aria-hidden className="h-4 w-4" />
                  </button>
                  <button type="button" aria-label={t("Delete place {{name}}", { name: p.name })} className={dangerBtn + " !px-3"} onClick={() => remove(p)}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <PlaceFormDialog
        open={editing !== null}
        pool={pool}
        data={data}
        place={editing?.place ?? null}
        onClose={() => setEditing(null)}
        onSave={async (input: PlaceInput) => {
          const ok = await attempt(
            () => (editing?.place ? desksApi.updatePlace(editing.place.id, input) : desksApi.createPlace(input)),
            t("Place saved."),
          );
          if (ok) setEditing(null);
          return ok;
        }}
      />
    </section>
  );
}
