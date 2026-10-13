// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { poolAccent } from "../poolAccent";
import { UserPicker } from "../components/UserPicker";
import { AdminTabs } from "../components/AdminTabs";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import type {
  AccessGroup,
  AccessGroupInput,
  AccessGroupMember,
  Paginated,
  ResourcePool,
} from "../types";
import { FormActionBar, sameFormValue } from "../components/FormActionBar";

const EMPTY: AccessGroupInput = {
  name: "",
  description: "",
  claim_key: "",
  claim_values: [],
  pools: [],
  lender_pools: [],
  is_admin: false,
};

function toInput(g: AccessGroup): AccessGroupInput {
  return {
    name: g.name,
    description: g.description,
    claim_key: g.claim_key,
    claim_values: g.claim_values,
    pools: g.pools,
    lender_pools: g.lender_pools,
    is_admin: g.is_admin,
  };
}

const isSystem = (g: AccessGroup) => g.system_pool !== null || g.system_admin;

const chipClass =
  "inline-block rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs text-slate-700 dark:text-slate-200";

/** A pool chip in the pool's accent colour (#16; unknown pools → neutral). */
function PoolChip({ label, accent }: { label: string; accent?: string | null }) {
  const a = poolAccent(accent);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs text-slate-700 dark:text-slate-200 ${a.border} ${a.tint}`}
    >
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${a.dot}`} />
      {label}
    </span>
  );
}

/** Whether a group has members beyond its manual ones (claim rule or the
 *  "Administratoren" system right) — those only show in the full list. */
const hasAutoMembers = (g: AccessGroup) =>
  (g.claim_key !== "" && g.claim_values.length > 0) || g.system_admin;

function useSourceLabel() {
  const { t } = useTranslation();
  return (s: AccessGroupMember["source"]) =>
    s === "manual" ? t("manual") : s === "claim" ? t("by rule") : t("system right");
}

function MemberList({ members }: { members: AccessGroupMember[] }) {
  const { t } = useTranslation();
  const sourceLabel = useSourceLabel();
  if (members.length === 0)
    return <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">–</p>;
  return (
    <ul className="mt-1 max-h-48 space-y-1 overflow-y-auto">
      {members.map((m) => (
        <li
          key={m.id}
          className={`flex flex-wrap items-center gap-2 text-xs ${
            m.is_active
              ? "text-slate-700 dark:text-slate-200"
              : "text-slate-600 dark:text-slate-300"
          }`}
        >
          <span>{m.name || m.username}</span>
          {m.email && <span className="text-slate-500 dark:text-slate-400">{m.email}</span>}
          <span className={chipClass}>{sourceLabel(m.source)}</span>
          {!m.is_active && <span className={chipClass}>{t("deactivated")}</span>}
        </li>
      ))}
    </ul>
  );
}

/** "Mitglieder" cell: the first manual members by name, then an expander
 *  that lazily loads the full effective list (manual, by rule, system right). */
function MembersCell({ group }: { group: AccessGroup }) {
  const { t } = useTranslation();
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<AccessGroupMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remaining = group.member_count - group.member_preview.length;
  const auto = hasAutoMembers(group);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && members === null) {
      setError(null);
      try {
        setMembers(await api.listAccessGroupMembers(group.id));
      } catch (err) {
        setError(err instanceof Error ? err.message : t("Loading failed."));
      }
    }
  }

  if (group.member_preview.length === 0 && !auto) return <span>–</span>;

  // Honest label: the preview and the count cover manual members only; when
  // rule/system members may exist, the expander says so instead of a number.
  const label = open
    ? t("Show less")
    : auto
      ? t("Show all members, incl. via rule or system right")
      : remaining > 0
        ? t("+{{count}} more", { count: remaining })
        : null;

  return (
    <div>
      {!open && group.member_preview.length > 0 && (
        <span className="text-slate-700 dark:text-slate-200">
          {group.member_preview.map((m) => m.name).join(", ")}
        </span>
      )}
      {label && (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={toggle}
          className={`${
            !open && group.member_preview.length > 0 ? "ml-1 " : ""
          }text-left text-xs font-medium text-slate-700 dark:text-slate-200 underline underline-offset-2 hover:text-slate-900 dark:hover:text-slate-100`}
        >
          {label}
        </button>
      )}
      <div id={panelId} hidden={!open}>
        {open && members === null && !error && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("Loading…")}</p>
        )}
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-300">{error}</p>}
        {members && <MemberList members={members} />}
      </div>
    </div>
  );
}

interface ManualMember {
  id: number;
  name: string;
  is_active: boolean;
}

const inputClass =
  "block w-full rounded-md border border-slate-300 dark:border-slate-600 dark:bg-slate-800 px-2 py-1 text-sm text-slate-900 dark:text-slate-100";

export function AdminAccessGroupsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<AccessGroup | "new" | null>(null);
  const groups = useFetch<Paginated<AccessGroup>>(
    () => api.listAccessGroups(),
    [version],
  );
  const pools = useFetch<Paginated<ResourcePool>>(() => api.listPools(), []);
  const accentById = new Map(
    (pools.data?.results ?? []).map((p) => [p.id, p.accent_color] as const),
  );

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);

  async function remove(group: AccessGroup) {
    if (
      !(await confirm({
        message: t("Delete access group “{{name}}”?", { name: group.name }),
        confirmLabel: t("Delete"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteAccessGroup(group.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Access groups")}</h2>
        {editing === null && (
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
          >
            {t("+ New group")}
          </button>
        )}
      </div>

      <p className="mb-4 text-xs text-slate-600 dark:text-slate-300">
        {t(
          "A pool with no access groups is open to everyone who is signed in. Once a pool is listed in at least one group, only members of those groups (plus the pool’s lenders and admins) can see and book it.",
        )}
      </p>

      {editing !== null && (
        <GroupForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          groupId={editing === "new" ? null : editing.id}
          system={editing !== "new" && isSystem(editing)}
          autoMembers={editing !== "new" && hasAutoMembers(editing)}
          pools={pools.data?.results ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {groups.loading && <Loading />}
      {groups.error && <ErrorBox message={groups.error} />}

      {groups.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs text-slate-600 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Pools")}</th>
                <th className="px-3 py-2">{t("Rights")}</th>
                <th className="px-3 py-2">{t("Claim rule")}</th>
                <th className="px-3 py-2">{t("Members")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {groups.data.results.map((g) => (
                <tr key={g.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 align-top font-medium text-slate-900 dark:text-slate-100">
                    {g.name}
                    {isSystem(g) && <span className={`ml-2 ${chipClass}`}>{t("System")}</span>}
                  </td>
                  <td className="px-3 py-2 align-top text-slate-600 dark:text-slate-300">
                    {g.pools.length ? (
                      <div className="flex flex-wrap gap-1">
                        {g.pools.map((id, i) => (
                          <PoolChip key={id} label={g.pool_names[i] ?? ""} accent={accentById.get(id)} />
                        ))}
                      </div>
                    ) : (
                      "–"
                    )}
                  </td>
                  <td className="px-3 py-2 align-top">
                    <div className="flex flex-wrap gap-1">
                      {g.is_admin && <span className={chipClass}>{t("Administrator")}</span>}
                      {g.lender_pools.map((id, i) => (
                        <PoolChip
                          key={id}
                          label={t("Lender: {{pool}}", { pool: g.lender_pool_names[i] ?? "" })}
                          accent={accentById.get(id)}
                        />
                      ))}
                      {!g.is_admin && g.lender_pool_names.length === 0 && (
                        <span className="text-slate-600 dark:text-slate-300">–</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 align-top text-slate-600 dark:text-slate-300">
                    {g.claim_key
                      ? `${g.claim_key} ∈ {${g.claim_values.join(", ")}}`
                      : "–"}
                  </td>
                  <td className="px-3 py-2 align-top text-slate-600 dark:text-slate-300">
                    <MembersCell key={`${g.id}-${version}`} group={g} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5">
                      <EditButton onClick={() => setEditing(g)} />
                      {!isSystem(g) && <DeleteButton onClick={() => remove(g)} />}
                    </div>
                  </td>
                </tr>
              ))}
              {groups.data.results.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t(
                      "No access groups yet — every pool is open to all signed-in users.",
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function GroupForm({
  initial,
  groupId,
  system,
  autoMembers,
  pools,
  onClose,
  onSaved,
}: {
  initial: AccessGroupInput;
  groupId: number | null;
  system: boolean;
  autoMembers?: boolean;
  pools: ResourcePool[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<AccessGroupInput>(initial);
  const [claimValuesText, setClaimValuesText] = useState(
    initial.claim_values.join(", "),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Manual members (editable, sent as ``members``) and the read-only ones via
  // rule / system right — loaded from the members endpoint for an existing
  // group. ``null`` while loading (or on a load error): ``members`` is then
  // left out of the save so nothing gets dropped by accident.
  const [manual, setManual] = useState<ManualMember[] | null>(groupId === null ? [] : null);
  const [initialManualIds, setInitialManualIds] = useState<number[]>([]);
  const [autoList, setAutoList] = useState<AccessGroupMember[]>([]);
  const [membersError, setMembersError] = useState<string | null>(null);

  useEffect(() => {
    if (groupId === null) return;
    let cancelled = false;
    api
      .listAccessGroupMembers(groupId)
      .then((rows) => {
        if (cancelled) return;
        const own = rows
          .filter((m) => m.source === "manual")
          .map((m) => ({ id: m.id, name: m.name || m.username, is_active: m.is_active }));
        setManual(own);
        setInitialManualIds(own.map((m) => m.id));
        setAutoList(rows.filter((m) => m.source !== "manual"));
      })
      .catch((err) => {
        if (!cancelled) setMembersError(err instanceof Error ? err.message : t("Loading failed."));
      });
    return () => {
      cancelled = true;
    };
  }, [groupId, t]);

  const manualIds = manual?.map((m) => m.id) ?? [];
  const membersChanged =
    manual !== null &&
    (manualIds.length !== initialManualIds.length ||
      manualIds.some((id) => !initialManualIds.includes(id)));
  const dirty =
    !sameFormValue(form, initial) ||
    claimValuesText !== initial.claim_values.join(", ") ||
    membersChanged;

  // Keep the advanced settings visible when the group already uses them.
  const advancedOpen =
    initial.lender_pools.length > 0 ||
    initial.is_admin ||
    initial.claim_key !== "" ||
    initial.claim_values.length > 0;

  function togglePool(id: number) {
    setForm((f) => ({
      ...f,
      pools: f.pools.includes(id)
        ? f.pools.filter((p) => p !== id)
        : [...f.pools, id],
    }));
  }

  function toggleLender(id: number) {
    setForm((f) => ({
      ...f,
      lender_pools: f.lender_pools.includes(id)
        ? f.lender_pools.filter((p) => p !== id)
        : [...f.lender_pools, id],
    }));
  }

  const hasRule = form.claim_key.trim() !== "" || claimValuesText.trim() !== "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!system && hasRule && form.is_admin) {
      setError(t("Administrator rights cannot be granted via a login rule – remove the rule first."));
      return;
    }
    setBusy(true);
    setError(null);
    const claim_values = claimValuesText
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    const payload: Partial<AccessGroupInput> = system
      ? { description: form.description, pools: form.pools }
      : { ...form, claim_values };
    if (membersChanged) payload.members = manualIds;
    try {
      if (groupId === null) await api.createAccessGroup(payload as AccessGroupInput);
      else await api.updateAccessGroup(groupId, payload);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mb-5 space-y-4 rounded-xl border border-slate-200 dark:border-slate-800 p-4"
    >
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {groupId === null
          ? t("New access group")
          : t("Edit {{name}}", { name: initial.name })}
      </h3>

      <label className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Name")}
        <input
          required
          disabled={system}
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          className={`mt-1 ${inputClass}`}
        />
      </label>
      {system && (
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {t("System group: name, rule and rights are managed automatically.")}
        </p>
      )}
      <label className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Description")}
        <textarea
          rows={2}
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          className={`mt-1 ${inputClass}`}
        />
      </label>

      <fieldset>
        <legend className="mb-1 text-xs font-medium text-slate-600 dark:text-slate-300">
          {t("Members")}
        </legend>
        {membersError && (
          <p className="text-xs text-red-600 dark:text-red-300">{membersError}</p>
        )}
        {manual === null && !membersError && (
          <p className="text-xs text-slate-600 dark:text-slate-300">{t("Loading…")}</p>
        )}
        {manual !== null && (
          <>
            {manual.length === 0 ? (
              <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">–</p>
            ) : (
              <ul className="mb-2 flex flex-wrap gap-1.5">
                {manual.map((m) => (
                  <li
                    key={m.id}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-0.5 pl-2.5 pr-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200"
                  >
                    {m.name}
                    {!m.is_active && (
                      <span className="text-slate-500 dark:text-slate-400">({t("deactivated")})</span>
                    )}
                    <button
                      type="button"
                      onClick={() => setManual((list) => list && list.filter((x) => x.id !== m.id))}
                      aria-label={t("Remove {{name}}", { name: m.name })}
                      className="rounded-full p-0.5 text-slate-500 hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                    >
                      <X aria-hidden className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <UserPicker
              label={t("Add member")}
              excludeIds={manualIds}
              onPick={(u) =>
                setManual((list) =>
                  list && !list.some((x) => x.id === u.id)
                    ? [...list, { id: u.id, name: u.display_name, is_active: true }]
                    : list,
                )
              }
            />
          </>
        )}
        {groupId !== null && manual !== null && (autoMembers || autoList.length > 0) && (
          <div className="mt-3">
            <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("Members via rule or system right")}
            </p>
            <MemberList members={autoList} />
          </div>
        )}
      </fieldset>

      <div>
        <p className="mb-1 text-xs font-medium text-slate-600 dark:text-slate-300">
          {t("Grants access to pools ({{count}} selected)", {
            count: form.pools.length,
          })}
        </p>
        <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-800 p-2">
          {pools.length === 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-300">{t("No pools available.")}</p>
          )}
          {pools.map((pool) => (
            <label
              key={pool.id}
              className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"
            >
              <input
                type="checkbox"
                checked={form.pools.includes(pool.id)}
                onChange={() => togglePool(pool.id)}
              />
              <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${poolAccent(pool.accent_color).dot}`} />
              {pool.name}
              <span className="text-xs text-slate-400 dark:text-slate-300">({pool.pool_id})</span>
            </label>
          ))}
        </div>
      </div>

      <details
        open={advancedOpen}
        className="rounded-md border border-slate-200 p-3 dark:border-slate-800"
      >
        <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-300">
          {t("Advanced settings")}
        </summary>
        <div className="mt-3 space-y-4">
          <div>
            <p className="mb-1 text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("Lender for pools ({{count}} selected)", { count: form.lender_pools.length })}
            </p>
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-800 p-2">
              {pools.length === 0 && (
                <p className="text-xs text-slate-400 dark:text-slate-300">{t("No pools available.")}</p>
              )}
              {pools.map((pool) => (
                <label
                  key={pool.id}
                  className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"
                >
                  <input
                    type="checkbox"
                    disabled={system}
                    checked={form.lender_pools.includes(pool.id)}
                    onChange={() => toggleLender(pool.id)}
                  />
                  <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${poolAccent(pool.accent_color).dot}`} />
                  {pool.name}
                  <span className="text-xs text-slate-400 dark:text-slate-300">({pool.pool_id})</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox"
                disabled={system || (hasRule && !form.is_admin)}
                checked={form.is_admin}
                onChange={(e) => setForm((f) => ({ ...f, is_admin: e.target.checked }))}
              />
              {t("Administrator")}
            </label>
            {hasRule && !system && (
              <p className={`mt-1 text-xs ${form.is_admin ? "text-red-600 dark:text-red-300" : "text-slate-600 dark:text-slate-300"}`}>
                {t("Administrator rights cannot be granted via a login rule – remove the rule first.")}
              </p>
            )}
          </div>

          <div className="rounded-md bg-slate-50 dark:bg-slate-800/50 p-3">
            <p className="mb-1 text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("Automatic membership via login claim (optional)")}
            </p>
            <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
              {t(
                "A login claim is information the single sign-on (SSO) sends about a person when they sign in — such as their department, study programme or group memberships. Fill this in to grant pool access automatically to everyone whose claim matches, instead of adding each person by hand.",
              )}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs text-slate-600 dark:text-slate-300">
                {t("Claim key")}
                <input
                  disabled={system}
                  value={form.claim_key}
                  onChange={(e) => setForm((f) => ({ ...f, claim_key: e.target.value }))}
                  placeholder={t("e.g. groups or department")}
                  className={`mt-1 ${inputClass}`}
                />
              </label>
              <label className="block text-xs text-slate-600 dark:text-slate-300">
                {t("Matching values (comma-separated)")}
                <input
                  disabled={system}
                  value={claimValuesText}
                  onChange={(e) => setClaimValuesText(e.target.value)}
                  placeholder={t("e.g. music, media")}
                  className={`mt-1 ${inputClass}`}
                />
              </label>
            </div>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-300">
              {t(
                "A signed-in user whose “{{claim}}” contains any of these values is automatically a member, in addition to those added manually on the Users tab.",
                { claim: form.claim_key || t("claim") },
              )}
            </p>
          </div>
        </div>
      </details>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      )}

      <FormActionBar saving={busy} onCancel={onClose} dirty={dirty} />
    </form>
  );
}
