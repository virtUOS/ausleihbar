// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
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

function MembersDisclosure({ group }: { group: AccessGroup }) {
  const { t } = useTranslation();
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<AccessGroupMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const sourceLabel = (s: AccessGroupMember["source"]) =>
    s === "manual" ? t("manual") : s === "claim" ? t("by rule") : t("system right");

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={toggle}
        className="text-left text-sm text-slate-700 dark:text-slate-200 underline-offset-2 hover:underline"
      >
        {members
          ? t("Members ({{count}})", { count: members.length })
          : t("Members ({{count}} manual)", { count: group.member_count })}
      </button>
      <div id={panelId} hidden={!open}>
        {open && members === null && !error && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("Loading…")}</p>
        )}
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-300">{error}</p>}
        {members && members.length === 0 && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">–</p>
        )}
        {members && members.length > 0 && (
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
        )}
      </div>
    </div>
  );
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
                    {g.pool_names.length ? g.pool_names.join(", ") : "–"}
                  </td>
                  <td className="px-3 py-2 align-top">
                    <div className="flex flex-wrap gap-1">
                      {g.is_admin && <span className={chipClass}>{t("Administrator")}</span>}
                      {g.lender_pool_names.map((n) => (
                        <span key={n} className={chipClass}>{t("Lender: {{pool}}", { pool: n })}</span>
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
                    <MembersDisclosure key={`${g.id}-${version}`} group={g} />
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
  pools,
  onClose,
  onSaved,
}: {
  initial: AccessGroupInput;
  groupId: number | null;
  system: boolean;
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
  const dirty =
    !sameFormValue(form, initial) ||
    claimValuesText !== initial.claim_values.join(", ");

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
              {pool.name}
              <span className="text-xs text-slate-400 dark:text-slate-300">({pool.pool_id})</span>
            </label>
          ))}
        </div>
      </div>

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

      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

      <FormActionBar saving={busy} onCancel={onClose} dirty={dirty} />
    </form>
  );
}
