// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../api";
import { AccessGroupPicker } from "../../components/AccessGroupPicker";
import { BottomSheet } from "../../components/BottomSheet";
import { WarningNotice } from "../../components/WarningNotice";
import type { AccessGroup, ResourcePool } from "../../types";
import { desksApi } from "../api";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import { FieldError, errorOf, fieldErrors } from "./batchPreview";

/** "" = not chosen yet, "none" = remove the assignment, else a pool id. */
type Choice = "" | "none" | number;

const isSystemGroup = (g: AccessGroup) =>
  g.system_pool !== null || g.system_admin || g.system_all || g.system_course !== null;

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
  roomFollowerIds,
  unassign = false,
  currentPool = null,
  onClose,
  onAssigned,
}: {
  open: boolean;
  /** The department all targets share now (preselected), else null. */
  currentPool?: number | null;
  /** Opened to remove the assignment: "no department" is preselected. */
  unassign?: boolean;
  roomIds: number[];
  placeIds: number[];
  /** Selected places in a selected room that follow it (not overridden). */
  roomFollowerIds: number[];
  onClose: () => void;
  onAssigned: (placesChanged: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={unassign ? t("Remove assignment") : t("Assign department")} onClose={onClose}>
      {open && (
        <AssignForm
          initialChoice={unassign ? "none" : (currentPool ?? "")}
          currentPool={currentPool}
          roomIds={roomIds}
          placeIds={placeIds}
          roomFollowerIds={roomFollowerIds}
          onClose={onClose}
          onAssigned={onAssigned}
        />
      )}
    </BottomSheet>
  );
}

function AssignForm({
  initialChoice,
  currentPool,
  roomIds,
  placeIds,
  roomFollowerIds,
  onClose,
  onAssigned,
}: {
  initialChoice: Choice;
  currentPool: number | null;
  roomIds: number[];
  placeIds: number[];
  roomFollowerIds: number[];
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

  const [choice, setChoice] = useState<Choice>(initialChoice);
  const [query, setQuery] = useState("");
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

  const currentAccess = pool === null ? [] : (groups ?? []).filter((g) => !g.system_all && g.pools.includes(pool));
  const currentAdmin = pool === null ? [] : (groups ?? []).filter((g) => g.lender_pools.includes(pool));
  // System groups ("Verleiher ‹Pool›", "Administratoren") are never offered.
  const offeredAccess = (groups ?? []).filter((g) => !currentAccess.includes(g) && !isSystemGroup(g));
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
    // A place that follows a selected room gets its department through the
    // room; sending it as well would make it deliberately different.
    const followers = new Set(roomFollowerIds);
    const sentPlaceIds = followRoom ? placeIds : placeIds.filter((id) => !followers.has(id));
    try {
      const { places_changed } = await desksApi.assign({
        ...(roomIds.length ? { room_ids: roomIds } : {}),
        ...(sentPlaceIds.length ? { place_ids: sentPlaceIds, follow_room: followRoom } : {}),
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

  // Without an access group the "needs an access group" error belongs next
  // to the access-group chooser.
  const poolError = errorOf(fields, "pool");
  const poolErrorAtAccess = pool !== null && currentAccess.length === 0;
  const selectError = poolErrorAtAccess ? null : poolError;
  const accessError = [poolErrorAtAccess ? poolError : null, errorOf(fields, "access_group_ids")]
    .filter(Boolean)
    .join(" ") || null;
  const adminError = errorOf(fields, "admin_group_ids");

  if (loadError) return <WarningNotice message={loadError} />;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-4"
    >
      <div>
        <p id="assign-pool-label" className={labelCls}>
          {t("Department")}
        </p>
        {followOnly ? (
          <p className="text-sm text-slate-700 dark:text-slate-200">{t("The room's department")}</p>
        ) : pools === null ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">{t("Loading…")}</p>
        ) : (
          <>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("Search pools…")}
              aria-label={t("Search pools…")}
              className={`${inputCls} mb-1`}
            />
            <div
              id="assign-pool"
              role="radiogroup"
              aria-labelledby="assign-pool-label"
              aria-invalid={!!selectError}
              aria-describedby={selectError ? "assign-pool-error" : undefined}
              className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700"
            >
              {[
                { value: "none" as Choice, label: t("No department (remove assignment)") },
                ...pools.map((p) => ({ value: p.id as Choice, label: p.name })),
              ]
                .filter(
                  (o) =>
                    o.value === choice ||
                    !query.trim() ||
                    o.label.toLowerCase().includes(query.trim().toLowerCase()),
                )
                .map((o) => (
                  <label
                    key={String(o.value)}
                    className={`flex min-h-[44px] cursor-pointer items-center gap-3 px-3 text-sm text-slate-800 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800/60 ${
                      o.value === choice ? "bg-brand-50 dark:bg-brand-900/30" : ""
                    }`}
                  >
                    <input
                      type="radio"
                      name="assign-pool"
                      className="h-5 w-5"
                      checked={o.value === choice}
                      onChange={() => choose(o.value)}
                    />
                    <span className="min-w-0 flex-1 truncate">{o.label}</span>
                    {o.value === currentPool && (
                      <span className="text-xs text-slate-600 dark:text-slate-300">{t("current")}</span>
                    )}
                  </label>
                ))}
            </div>
          </>
        )}
        <FieldError id="assign-pool-error" message={selectError} />
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
          <div>
            <AccessGroupPicker
              groups={groups === null ? null : [...currentAccess, ...offeredAccess]}
              selected={[...currentAccess.map((g) => g.id), ...accessIds]}
              lockedIds={currentAccess.map((g) => g.id)}
              onToggle={(id) => setAccessIds((l) => l.filter((x) => x !== id))}
              onAdd={(id) => setAccessIds((l) => [...l, id])}
              legend={t("Access groups of the pool")}
              hint={[
                t("Members may see and book the department's places. Groups are only added here, never removed."),
                t("Applies to the whole pool, lending included."),
                currentAccess.length === 0
                  ? t("Visible to everyone so far – after adding, only to group members.")
                  : null,
              ]
                .filter(Boolean)
                .join(" ")}
            />
            <FieldError id="assign-access-error" message={accessError} />
          </div>
          <div>
            <AccessGroupPicker
              groups={groups === null ? null : [...currentAdmin, ...offeredAdmin]}
              selected={[...currentAdmin.map((g) => g.id), ...adminIds]}
              lockedIds={currentAdmin.map((g) => g.id)}
              onToggle={(id) => setAdminIds((l) => l.filter((x) => x !== id))}
              onAdd={(id) => setAdminIds((l) => [...l, id])}
              legend={t("Admin groups of the pool")}
              hint={[
                t("Members administer the department. Groups are only added here, never removed."),
                t("Members also get lender rights for this pool."),
              ].join(" ")}
            />
            <FieldError id="assign-admin-error" message={adminError} />
          </div>
        </div>
      )}

      <p className="text-sm text-slate-700 dark:text-slate-200">{t("Existing bookings run on until they end.")}</p>
      {general && <WarningNotice message={general} />}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !ready} className={primaryBtn}>
          {!followOnly && choice === "none" ? t("Remove assignment") : t("Assign")}
        </button>
        <button type="button" onClick={onClose} className={secondaryBtn}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
