// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
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
  Paginated,
  ResourcePool,
} from "../types";

const EMPTY: AccessGroupInput = {
  name: "",
  description: "",
  claim_key: "",
  claim_values: [],
  pools: [],
};

function toInput(g: AccessGroup): AccessGroupInput {
  return {
    name: g.name,
    description: g.description,
    claim_key: g.claim_key,
    claim_values: g.claim_values,
    pools: g.pools,
  };
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

      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t(
          "A pool with no access groups is open to everyone who is signed in. Once a pool is listed in at least one group, only members of those groups (plus the pool’s lenders and admins) can see and book it.",
        )}
      </p>

      {editing !== null && (
        <GroupForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          groupId={editing === "new" ? null : editing.id}
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
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Pools")}</th>
                <th className="px-3 py-2">{t("Claim rule")}</th>
                <th className="px-3 py-2">{t("Members")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {groups.data.results.map((g) => (
                <tr key={g.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{g.name}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {g.pool_names.length ? g.pool_names.join(", ") : "–"}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {g.claim_key
                      ? `${g.claim_key} ∈ {${g.claim_values.join(", ")}}`
                      : "–"}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{g.member_count}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5">
                      <EditButton onClick={() => setEditing(g)} />
                      <DeleteButton onClick={() => remove(g)} />
                    </div>
                  </td>
                </tr>
              ))}
              {groups.data.results.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
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
  pools,
  onClose,
  onSaved,
}: {
  initial: AccessGroupInput;
  groupId: number | null;
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

  function togglePool(id: number) {
    setForm((f) => ({
      ...f,
      pools: f.pools.includes(id)
        ? f.pools.filter((p) => p !== id)
        : [...f.pools, id],
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const claim_values = claimValuesText
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    const payload = { ...form, claim_values };
    try {
      if (groupId === null) await api.createAccessGroup(payload);
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

      <label className="block text-xs text-slate-500 dark:text-slate-400">
        {t("Name")}
        <input
          required
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          className={`mt-1 ${inputClass}`}
        />
      </label>
      <label className="block text-xs text-slate-500 dark:text-slate-400">
        {t("Description")}
        <textarea
          rows={2}
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          className={`mt-1 ${inputClass}`}
        />
      </label>

      <div>
        <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          {t("Grants access to pools ({{count}} selected)", {
            count: form.pools.length,
          })}
        </p>
        <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-800 p-2">
          {pools.length === 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500">{t("No pools available.")}</p>
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
              <span className="text-xs text-slate-400 dark:text-slate-500">({pool.pool_id})</span>
            </label>
          ))}
        </div>
      </div>

      <div className="rounded-md bg-slate-50 dark:bg-slate-800/50 p-3">
        <p className="mb-1 text-xs font-medium text-slate-600 dark:text-slate-300">
          {t("Automatic membership via login claim (optional)")}
        </p>
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
          {t(
            "A login claim is information the single sign-on (SSO) sends about a person when they sign in — such as their department, study programme or group memberships. Fill this in to grant pool access automatically to everyone whose claim matches, instead of adding each person by hand.",
          )}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-xs text-slate-500 dark:text-slate-400">
            {t("Claim key")}
            <input
              value={form.claim_key}
              onChange={(e) => setForm((f) => ({ ...f, claim_key: e.target.value }))}
              placeholder={t("e.g. groups or department")}
              className={`mt-1 ${inputClass}`}
            />
          </label>
          <label className="block text-xs text-slate-500 dark:text-slate-400">
            {t("Matching values (comma-separated)")}
            <input
              value={claimValuesText}
              onChange={(e) => setClaimValuesText(e.target.value)}
              placeholder={t("e.g. music, media")}
              className={`mt-1 ${inputClass}`}
            />
          </label>
        </div>
        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
          {t(
            "A signed-in user whose “{{claim}}” contains any of these values is automatically a member, in addition to those added manually on the Users tab.",
            { claim: form.claim_key || t("claim") },
          )}
        </p>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Saving…") : t("Save")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
