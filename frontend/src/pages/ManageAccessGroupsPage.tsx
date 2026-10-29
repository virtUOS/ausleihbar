// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { ManageTabs } from "../components/ManageTabs";
import { ErrorBox, Loading } from "../components/Status";
import { PoolChip } from "../components/PoolChip";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { UserPicker, type PickedUser } from "../components/UserPicker";
import {
  AccessGroupMemberList,
  memberChipClass,
} from "../components/AccessGroupMemberList";
import type { AccessGroupMember, MaintainableGroup } from "../types";

/** The lending desk's person lookup (min. 3 characters, #160). */
const searchPeople = (term: string): Promise<PickedUser[]> =>
  api.searchBorrowers(term).then((found) =>
    found.map((u) => ({
      id: u.id,
      username: u.username,
      display_name: (u.full_name ?? "").trim() || u.username,
      email: u.email,
    })),
  );

const errorText = (err: unknown, fallback: string) =>
  err instanceof Error ? err.message : fallback;

/** One access group: its pools, the claim rule (if any) and its members —
 *  manual ones removable, claim ones tagged "automatisch". */
function GroupCard({
  group,
  onChanged,
}: {
  group: MaintainableGroup;
  onChanged: (next: MaintainableGroup | null) => void;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [showAuto, setShowAuto] = useState(false);

  async function add(user: PickedUser) {
    if (adding) return;
    setError(null);
    setAdding(true);
    try {
      onChanged(await api.addGroupMember(group.id, user.id));
      toast.success(
        t("{{name}} added to {{group}}.", { name: user.display_name, group: group.name }),
      );
    } catch (err) {
      setError(errorText(err, t("Save failed.")));
      // 404: the group is no longer maintainable for us — reload so it goes.
      if (err instanceof ApiError && err.status === 404) onChanged(null);
    } finally {
      setAdding(false);
    }
  }

  async function remove(m: AccessGroupMember) {
    const name = m.name || m.username;
    const ok = await confirm({
      message: t(
        "Remove {{name}} from {{group}}? They will then no longer see this group's pools.",
        { name, group: group.name },
      ),
      confirmLabel: t("Remove"),
      danger: true,
    });
    if (!ok) return;
    setError(null);
    setBusyId(m.id);
    try {
      await api.removeGroupMember(group.id, m.id);
      onChanged(null); // 204: reload, the person may still be a claim member
      toast.success(t("{{name}} removed from {{group}}.", { name, group: group.name }));
    } catch (err) {
      setError(errorText(err, t("Save failed.")));
    } finally {
      setBusyId(null);
    }
  }

  const headingId = `access-group-${group.id}`;
  const autoId = `access-group-${group.id}-auto`;
  // Claim rules may match thousands of accounts: list the manual members,
  // collapse the automatic ones (#171). Manual + claim counts as manual.
  const manual = group.members.filter((m) => m.source === "manual");
  const auto = group.members.filter((m) => m.source !== "manual");
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
    >
      <h3 id={headingId} className="text-base font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {group.name}
      </h3>
      {group.description && (
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{group.description}</p>
      )}
      {group.pools.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={t("Pools")}>
          {group.pools.map((p) => (
            <li key={p.id}>
              <PoolChip
                accent={p.accent_color}
                label={p.managed ? p.name : t("{{pool}} (not your pool)", { pool: p.name })}
              />
            </li>
          ))}
        </ul>
      )}
      {group.has_claim_rule && group.claim_summary && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {t("Also a member automatically: everyone with {{rule}}", {
            rule: group.claim_summary,
          })}
        </p>
      )}

      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {t("Members")}
      </h4>
      {(manual.length > 0 || auto.length === 0) && (
        <AccessGroupMemberList
          members={manual}
          scroll={false}
          onRemove={remove}
          busyId={busyId}
        />
      )}
      {auto.length > 0 && (
        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {t("{{count}} people automatically via the login rule", { count: auto.length })}
          {" · "}
          <button
            type="button"
            aria-expanded={showAuto}
            aria-controls={autoId}
            onClick={() => setShowAuto((v) => !v)}
            className="font-medium text-slate-700 underline underline-offset-2 hover:text-slate-900 dark:text-slate-200 dark:hover:text-slate-100"
          >
            {showAuto ? t("hide") : t("show")}
          </button>
        </div>
      )}
      <div id={autoId} hidden={!showAuto}>
        {showAuto && auto.length > 0 && (
          <AccessGroupMemberList
            members={auto}
            tag={() => <span className={memberChipClass}>{t("automatic")}</span>}
          />
        )}
      </div>

      <div className="mt-4">
        <UserPicker
          label={t("Add person")}
          onPick={add}
          search={searchPeople}
          minChars={3}
          excludeIds={manual.map((m) => m.id)}
        />
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
    </section>
  );
}

/**
 * Lending desk "Zugriffsgruppen" (#171): lenders maintain the manual members
 * of the pure access groups of their pools. Groups that grant rights stay
 * with the admins; the server decides which groups show up here.
 */
export function ManageAccessGroupsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [groups, setGroups] = useState<MaintainableGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listMaintainableGroups()
      .then((data) => {
        setGroups(data);
        setError(null);
      })
      .catch((err) => setError(errorText(err, t("Loading failed."))));
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (user && !user.is_lender && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  function changed(next: MaintainableGroup | null) {
    if (next) setGroups((gs) => gs?.map((g) => (g.id === next.id ? next : g)) ?? gs);
    else load();
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <h2 className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Access groups")}
      </h2>
      <p className="mb-4 mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-300">
        {t(
          "Who may see and book the items of your pools? Here you maintain the members of your pools' access groups; the groups themselves are created by the administration.",
        )}
      </p>

      {error && <ErrorBox message={error} />}
      {!error && groups === null && <Loading />}
      {groups !== null && groups.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
          <p>
            {t(
              "There is no access group for your pools. Access groups are created by the administration.",
            )}
          </p>
          {user?.is_staff && (
            <Link
              to="/admin/access-groups"
              className="mt-2 inline-block font-medium text-slate-700 underline underline-offset-2 hover:text-slate-900 dark:text-slate-200 dark:hover:text-slate-100"
            >
              {t("Manage access groups")}
            </Link>
          )}
        </div>
      )}
      {groups !== null && groups.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {groups.map((g) => (
            <GroupCard key={g.id} group={g} onChanged={changed} />
          ))}
        </div>
      )}
    </div>
  );
}
