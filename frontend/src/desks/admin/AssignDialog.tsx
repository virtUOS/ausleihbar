// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../api";
import { AccessGroupChooser } from "../../components/AccessGroupChooser";
import { BottomSheet } from "../../components/BottomSheet";
import { WarningNotice } from "../../components/WarningNotice";
import type { AccessGroup, ResourcePool } from "../../types";
import { desksApi } from "../api";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import { FieldError, errorOf, fieldErrors } from "./batchPreview";

/** "" = not chosen yet, "none" = remove the assignment, else a pool id. */
type Choice = "" | "none" | number;

const isSystemGroup = (g: AccessGroup) => g.system_pool !== null || g.system_admin;

/**
 * Assign the selected rooms and places to a department (app admins). Groups
 * are only ever added: the department's current access and admin groups are
 * listed read-only, further ones can be ticked. Selected places either get
 * the department as their own or follow their room again.
 */
export function AssignDialog({
  open,
  roomIds,
  placeIds,
  onClose,
  onAssigned,
}: {
  open: boolean;
  roomIds: number[];
  placeIds: number[];
  onClose: () => void;
  onAssigned: (placesChanged: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={t("Assign department")} onClose={onClose}>
      {open && <AssignForm roomIds={roomIds} placeIds={placeIds} onClose={onClose} onAssigned={onAssigned} />}
    </BottomSheet>
  );
}

function AssignForm({
  roomIds,
  placeIds,
  onClose,
  onAssigned,
}: {
  roomIds: number[];
  placeIds: number[];
  onClose: () => void;
  onAssigned: (placesChanged: number) => void;
}) {
  const { t } = useTranslation();
  // Loaded on every opening: a previous assignment may have added groups.
  const [pools, setPools] = useState<ResourcePool[] | null>(null);
  const [groups, setGroups] = useState<AccessGroup[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([api.listPools({ pageSize: 2000 }), api.listAccessGroups()]).then(
      ([p, g]) => {
        if (!live) return;
        setPools(p.results.filter((x) => x.is_active).sort((a, b) => a.name.localeCompare(b.name)));
        setGroups(g.results);
      },
      (e: unknown) => live && setLoadError(e instanceof Error ? e.message : t("The request failed.")),
    );
    return () => {
      live = false;
    };
  }, [t]);

  const [choice, setChoice] = useState<Choice>("");
  const [followRoom, setFollowRoom] = useState(false);
  const [accessIds, setAccessIds] = useState<number[]>([]);
  const [adminIds, setAdminIds] = useState<number[]>([]);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Only places, following their room: they take the room's department, so
  // there is nothing to choose.
  const followOnly = followRoom && roomIds.length === 0;
  const pool = !followOnly && typeof choice === "number" ? choice : null;
  const ready = followOnly || choice !== "";

  const currentAccess = pool === null ? [] : (groups ?? []).filter((g) => g.pools.includes(pool));
  const currentAdmin = pool === null ? [] : (groups ?? []).filter((g) => g.lender_pools.includes(pool));
  const offeredAccess = (groups ?? []).filter((g) => !currentAccess.includes(g));
  const offeredAdmin = (groups ?? []).filter((g) => !currentAdmin.includes(g) && !isSystemGroup(g));

  function choose(value: Choice) {
    setChoice(value);
    // Groups to add belong to the department they were ticked for.
    setAccessIds([]);
    setAdminIds([]);
    setFields({});
    setGeneral(null);
  }

  async function submit() {
    if (busy || !ready) return;
    setBusy(true);
    setFields({});
    setGeneral(null);
    try {
      const { places_changed } = await desksApi.assign({
        ...(roomIds.length ? { room_ids: roomIds } : {}),
        ...(placeIds.length ? { place_ids: placeIds, follow_room: followRoom } : {}),
        pool,
        ...(pool !== null && accessIds.length ? { access_group_ids: accessIds } : {}),
        ...(pool !== null && adminIds.length ? { admin_group_ids: adminIds } : {}),
      });
      onAssigned(places_changed);
    } catch (e) {
      const { fields: f, general: g } = fieldErrors(e);
      // Errors without a place of their own in the form go to the notice.
      const rest = errorOf(f, "room_ids", "place_ids", "follow_room");
      setFields(f);
      setGeneral([g, rest].filter(Boolean).join(" ") || null);
      setBusy(false);
    }
  }

  if (loadError) return <WarningNotice message={loadError} />;

  const groupList = (title: string, list: AccessGroup[]) => (
    <div>
      <p className={labelCls}>{title}</p>
      <p className="text-sm text-slate-800 dark:text-slate-200">
        {list.length ? list.map((g) => g.name).join(", ") : t("none")}
      </p>
    </div>
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-4"
    >
      <div>
        <label htmlFor="assign-pool" className={labelCls}>
          {t("Department")}
        </label>
        <select
          id="assign-pool"
          value={followOnly ? "" : String(choice)}
          disabled={followOnly || pools === null}
          onChange={(e) => {
            const v = e.target.value;
            choose(v === "" ? "" : v === "none" ? "none" : Number(v));
          }}
          aria-invalid={!!errorOf(fields, "pool")}
          aria-describedby="assign-pool-error"
          className={inputCls}
        >
          <option value="" disabled={!followOnly}>
            {followOnly ? t("The room's department") : pools === null ? t("Loading…") : t("Choose a department…")}
          </option>
          <option value="none">{t("No department (remove assignment)")}</option>
          {(pools ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <FieldError id="assign-pool-error" message={errorOf(fields, "pool")} />
        <Link
          to="/admin/pools"
          className="mt-1 inline-block text-xs font-medium text-brand-700 hover:underline dark:text-brand-300"
        >
          {t("Create a new department")}
        </Link>
      </div>

      {roomIds.length > 0 && (
        <p className="text-sm text-slate-700 dark:text-slate-200">
          {t("Rooms pass their department on to their places, except to deliberately different ones.")}
        </p>
      )}

      {placeIds.length > 0 && (
        <label className="flex min-h-[44px] items-start gap-3 text-sm text-slate-800 dark:text-slate-200">
          <input
            type="checkbox"
            className="mt-0.5 h-5 w-5"
            checked={followRoom}
            onChange={(e) => {
              setFollowRoom(e.target.checked);
              setFields({});
              setGeneral(null);
            }}
          />
          <span>
            {t("Places follow their room again")}
            <span className="block text-xs text-slate-600 dark:text-slate-300">
              {followRoom
                ? t("The selected places take their room's department.")
                : t("Otherwise the selected places get the chosen department as their own (deliberately different).")}
            </span>
          </span>
        </label>
      )}

      {pool !== null && (
        <div className="flex flex-col gap-4 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
          {groupList(t("Current access groups"), currentAccess)}
          {groupList(t("Current admin groups"), currentAdmin)}
          <div>
            <AccessGroupChooser
              groups={groups === null ? null : offeredAccess}
              selected={accessIds}
              onChange={setAccessIds}
              label={t("Add access group")}
              description={t("Members may see and book the department's places. Groups are only added here, never removed.")}
              emptyLabel={t("No further groups to add.")}
            />
            <FieldError id="assign-access-error" message={errorOf(fields, "access_group_ids")} />
          </div>
          <div>
            <AccessGroupChooser
              groups={groups === null ? null : offeredAdmin}
              selected={adminIds}
              onChange={setAdminIds}
              label={t("Add admin group")}
              description={t("Members administer the department. Groups are only added here, never removed.")}
              emptyLabel={t("No further groups to add.")}
            />
            <FieldError id="assign-admin-error" message={errorOf(fields, "admin_group_ids")} />
          </div>
        </div>
      )}

      <p className="text-sm text-slate-700 dark:text-slate-200">{t("Existing bookings run on until they end.")}</p>
      {general && <WarningNotice message={general} />}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !ready} className={primaryBtn}>
          {t("Assign")}
        </button>
        <button type="button" onClick={onClose} className={secondaryBtn}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
