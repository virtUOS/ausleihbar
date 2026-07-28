// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ListToolbar } from "../components/ListToolbar";
import { Pager } from "../components/Pager";
import { EditButton } from "../components/RowActions";
import { ErrorBox, Loading } from "../components/Status";
import { UserBookingHistory } from "../components/UserBookingHistory";
import { UserStrikes } from "../components/UserStrikes";
import type { AccessGroup, ManageUser, Paginated, ResourcePool } from "../types";

function RoleBadges({
  user,
  onFilter,
}: {
  user: ManageUser;
  onFilter?: (role: string) => void;
}) {
  const { t } = useTranslation();
  function Badge({
    role,
    className,
    children,
  }: {
    role?: string;
    className: string;
    children: React.ReactNode;
  }) {
    const base = `rounded-full px-2 py-0.5 text-xs font-semibold ${className}`;
    if (role && onFilter) {
      return (
        <button
          type="button"
          title={t("Filter by {{role}}", { role })}
          onClick={(e) => {
            e.stopPropagation();
            onFilter(role);
          }}
          className={`${base} hover:ring-2 hover:ring-slate-300 dark:hover:ring-slate-600`}
        >
          {children}
        </button>
      );
    }
    return <span className={base}>{children}</span>;
  }

  return (
    <div className="flex flex-wrap gap-1">
      {user.is_admin && (
        <Badge role="admin" className="bg-purple-100 text-purple-800 dark:bg-purple-950/50 dark:text-purple-300">
          {t("Admin")}
        </Badge>
      )}
      {user.is_lender && (
        <Badge role="lender" className="bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300">
          {t("Lender")} · {user.managed_pools.length}
        </Badge>
      )}
      {!user.is_admin && !user.is_lender && (
        <Badge role="borrower" className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {t("Borrower")}
        </Badge>
      )}
      {!user.is_active && (
        <Badge role="inactive" className="bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {t("Inactive")}
        </Badge>
      )}
      {user.is_blocked && (
        <Badge role="blocked" className="bg-red-600 text-white">
          {t("Blocked")}
        </Badge>
      )}
      {user.active_strikes > 0 && !user.is_blocked && (
        <Badge className="bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
          {t("{{count}} strike", { count: user.active_strikes })}
        </Badge>
      )}
    </div>
  );
}

export function AdminUsersPage() {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const [version, setVersion] = useState(0);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<ManageUser | null>(null);

  // Debounce the search box, and reset to page 1 on any filter change.
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => setPage(1), [query, roleFilter]);

  const users = useFetch<Paginated<ManageUser>>(
    () =>
      api.listUsers({
        search: query || undefined,
        role: roleFilter || undefined,
        page,
      }),
    [query, roleFilter, version, page],
  );
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000 }),
    [],
  );
  const groups = useFetch<Paginated<AccessGroup>>(() => api.listAccessGroups(), []);

  if (me && !me.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      {!editing && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Users")}</h2>
            {roleFilter && (
              <button
                type="button"
                onClick={() => setRoleFilter(null)}
                className="rounded-full bg-slate-900 px-2 py-0.5 text-xs font-medium text-white"
                title={t("Clear filter")}
              >
                {roleFilter} ✕
              </button>
            )}
          </div>
        </div>
      )}

      {!editing && (
        <ListToolbar
          search={search}
          onSearch={setSearch}
          placeholder={t("Search name or email…")}
        />
      )}

      {editing && (
        <UserForm
          user={editing}
          pools={pools.data?.results ?? []}
          groups={groups.data?.results ?? []}
          isSelf={me?.username === editing.username}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {users.loading && <Loading />}
      {users.error && <ErrorBox message={users.error} />}

      {users.data && !editing && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("User")}</th>
                <th className="px-3 py-2">{t("Email")}</th>
                <th className="px-3 py-2">{t("Roles")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.data.results.map((u) => (
                <tr
                  key={u.id}
                  onClick={() => setEditing(u)}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <td className="px-3 py-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">{u.username}</span>
                    {u.full_name && (
                      <span className="text-slate-500 dark:text-slate-400"> · {u.full_name}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{u.email || "–"}</td>
                  <td className="px-3 py-2">
                    <RoleBadges user={u} onFilter={setRoleFilter} />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-0.5">
                      <EditButton label={t("Details")} onClick={() => setEditing(u)} />
                    </div>
                  </td>
                </tr>
              ))}
              {users.data.results.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                    {t("No users found.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {users.data && !editing && (
        <Pager
          list={{
            page,
            count: users.data?.count ?? 0,
            hasPrev: Boolean(users.data?.previous),
            hasNext: Boolean(users.data?.next),
            setPage,
          }}
        />
      )}
    </div>
  );
}

function UserForm({
  user,
  pools,
  groups,
  isSelf,
  onClose,
  onSaved,
}: {
  user: ManageUser;
  pools: ResourcePool[];
  groups: AccessGroup[];
  isSelf: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [isAdmin, setIsAdmin] = useState(user.is_admin);
  const [isActive, setIsActive] = useState(user.is_active);
  const [poolIds, setPoolIds] = useState<number[]>(
    user.managed_pools.map((m) => m.resource_pool),
  );
  const [groupIds, setGroupIds] = useState<number[]>(
    user.groups.map((g) => g.id),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function togglePool(id: number) {
    setPoolIds((ids) =>
      ids.includes(id) ? ids.filter((p) => p !== id) : [...ids, id],
    );
  }

  function toggleGroup(id: number) {
    setGroupIds((ids) =>
      ids.includes(id) ? ids.filter((g) => g !== id) : [...ids, id],
    );
  }

  function sameSet(a: number[], b: number[]) {
    return a.length === b.length && a.every((x) => b.includes(x));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const roleChanged =
        isAdmin !== user.is_admin || isActive !== user.is_active;
      if (roleChanged) {
        await api.updateUserRole(user.id, { is_admin: isAdmin, is_active: isActive });
      }
      const originalPools = user.managed_pools.map((m) => m.resource_pool);
      if (!sameSet(poolIds, originalPools)) {
        await api.setUserPools(user.id, poolIds);
      }
      const originalGroups = user.groups.map((g) => g.id);
      if (!sameSet(groupIds, originalGroups)) {
        await api.setUserGroups(user.id, groupIds);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    <form
      onSubmit={submit}
      className="mb-5 space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {user.username} · {t("details")}
        {user.full_name && <span className="text-slate-500 dark:text-slate-400"> ({user.full_name})</span>}
      </h3>

      <div className="space-y-2">
        <label
          className={`flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 ${
            user.admin_via_oidc ? "opacity-50" : ""
          }`}
        >
          <input
            type="checkbox"
            checked={isAdmin}
            disabled={isSelf || user.admin_via_oidc}
            onChange={(e) => setIsAdmin(e.target.checked)}
          />
          {t("Admin (full access to all pools and management)")}
        </label>
        {user.admin_via_oidc && (
          <p className="ml-6 text-xs text-slate-500 dark:text-slate-400">
            {t("Admin rights come from the identity provider group and can't be changed here.")}
          </p>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={isActive}
            disabled={isSelf}
            onChange={(e) => setIsActive(e.target.checked)}
          />
          {t("Account active (uncheck to block sign-in)")}
        </label>
        {isSelf && (
          <p className="text-xs text-slate-400 dark:text-slate-500">
            {t("You can’t change your own admin status or deactivate yourself.")}
          </p>
        )}
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          {t("Lender for pools ({{count}} selected)", { count: poolIds.length })}
        </p>
        <p className="mb-2 text-xs text-slate-400 dark:text-slate-500">
          {t(
            "A user who manages at least one pool is a lender and can run the lending desk for those pools.",
          )}
        </p>
        <div className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-slate-200 p-2 dark:border-slate-800">
          {pools.length === 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500">{t("No pools available.")}</p>
          )}
          {pools.map((pool) => (
            <label
              key={pool.id}
              className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300"
            >
              <input
                type="checkbox"
                checked={poolIds.includes(pool.id)}
                onChange={() => togglePool(pool.id)}
              />
              {pool.name}
              <span className="text-xs text-slate-400 dark:text-slate-500">({pool.pool_id})</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          {t("Member of access groups ({{count}} selected)", {
            count: groupIds.length,
          })}
        </p>
        <p className="mb-2 text-xs text-slate-400 dark:text-slate-500">
          {t(
            "Membership grants access to the pools assigned to each group. Some users may also match a group automatically via their login claims — information the single sign-on sends at login, such as department or study programme.",
          )}
        </p>
        <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-slate-200 p-2 dark:border-slate-800">
          {groups.length === 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500">{t("No access groups defined yet.")}</p>
          )}
          {groups.map((group) => (
            <label
              key={group.id}
              className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300"
            >
              <input
                type="checkbox"
                checked={groupIds.includes(group.id)}
                onChange={() => toggleGroup(group.id)}
              />
              {group.name}
            </label>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

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
          className="rounded-full border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {t("Cancel")}
        </button>
      </div>
    </form>
    <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Strikes & suspension")}
      </h3>
      <UserStrikes user={user} />
    </section>
    <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Booking history")}</h3>
      <UserBookingHistory userId={user.id} />
    </section>
    </>
  );
}
