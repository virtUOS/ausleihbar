// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { formatDate } from "../dates";
import { ManageTabs } from "../components/ManageTabs";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { DeleteButton } from "../components/RowActions";
import { Switch } from "../components/Switch";
import { PersonalPoolBadge } from "../components/PersonalPoolBadge";
import { PoolChip } from "../components/PoolChip";
import {
  NoOpeningHoursHint,
  PoolForm,
  hasNoOpeningHours,
  toPoolInput,
} from "../components/PoolForm";
import type { Paginated, PoolCourse, ResourcePool } from "../types";

const linkButton =
  "inline-flex items-center rounded-full border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

function NotAuthorized() {
  const { t } = useTranslation();
  return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
}

function Frame({ children, showPoolScope = false }: { children: React.ReactNode; showPoolScope?: boolean }) {
  const { t } = useTranslation();
  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs showPoolScope={showPoolScope} />
      {children}
    </div>
  );
}

/** Lending area "Pools & Kurse" (`/manage/pools`): the pools the user runs,
 *  each leading to its linked LMS courses and — for the owner of a personal
 *  pool (and admins) — its settings. */
export function ManagePoolsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000, lending: true }),
    [],
  );

  if (user && !user.is_lender && !user.is_staff) return <NotAuthorized />;

  const rows = pools.data?.results ?? [];

  return (
    <Frame showPoolScope>
      <h2 className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Pools & courses")}</h2>
      <p className="mb-4 mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-300">
        {t(
          "Your pools and the LMS courses linked to them. Members of an active course may see and book the pool.",
        )}
      </p>
      {pools.loading && <Loading />}
      {pools.error && <ErrorBox message={pools.error} />}
      {pools.data && rows.length === 0 && <Empty label={t("You don't run any pool yet.")} />}
      {rows.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {rows.map((pool) => (
            <li key={pool.id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-start">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <PoolChip label={pool.name} accent={pool.accent_color} />
                  {pool.is_personal && <PersonalPoolBadge owner={pool.owner} />}
                  {!pool.is_active && (
                    <span className="text-xs text-slate-500 dark:text-slate-400">{t("Inactive")}</span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                  {pool.is_restricted
                    ? t("Visible to members of its courses and access groups.")
                    : t("Visible to everyone signed in.")}
                </p>
                {pool.is_personal && hasNoOpeningHours(pool.opening_hours) && (
                  <NoOpeningHoursHint className="mt-2" />
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
                <Link to={`/manage/pools/${pool.id}/courses`} className={linkButton}>
                  {t("Courses")}
                </Link>
                {pool.can_edit_settings && (
                  <Link to={`/manage/pools/${pool.id}/settings`} className={linkButton}>
                    {t("Settings")}
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Frame>
  );
}

/** Back link + pool heading shared by the course and settings pages. */
function PoolHeading({ pool, title }: { pool: ResourcePool; title: string }) {
  const { t } = useTranslation();
  return (
    <>
      <Link
        to="/manage/pools"
        className="text-sm font-medium text-brand-700 hover:underline dark:text-brand-300"
      >
        {t("← Pools & courses")}
      </Link>
      <h2 className="mt-2 flex flex-wrap items-center gap-2 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {title}
        {pool.is_personal && <PersonalPoolBadge owner={pool.owner} />}
      </h2>
    </>
  );
}

/** Linked LMS courses of one pool (`/manage/pools/:id/courses`): switch a
 *  course off (members keep their place but lose access) or remove it. */
export function ManagePoolCoursesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const confirm = useConfirm();
  const toast = useToast();
  const poolId = Number(useParams().id);
  const pool = useFetch<ResourcePool>(() => api.getManagePool(poolId), [poolId]);
  const [courses, setCourses] = useState<PoolCourse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listPoolCourses(poolId)
      .then((rows) => {
        if (!cancelled) setCourses(rows);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t("Loading failed."));
      });
    return () => {
      cancelled = true;
    };
  }, [poolId, t]);

  if (user && !user.is_lender && !user.is_staff) return <NotAuthorized />;

  async function toggle(course: PoolCourse, next: boolean) {
    setBusyId(course.id);
    try {
      const saved = await api.updatePoolCourse(poolId, course.id, { is_active: next });
      setCourses((list) => list?.map((c) => (c.id === saved.id ? saved : c)) ?? list);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(course: PoolCourse) {
    if (
      !(await confirm({
        message: t(
          "Remove the course “{{title}}” from this pool? Its members lose access unless another course or group grants it. Opening Ausleihbar from the course again as a teacher links it anew.",
          { title: course.title || course.context_id },
        ),
        confirmLabel: t("Remove"),
        danger: true,
      }))
    )
      return;
    setBusyId(course.id);
    try {
      await api.deletePoolCourse(poolId, course.id);
      setCourses((list) => list?.filter((c) => c.id !== course.id) ?? list);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Frame>
      {pool.loading && <Loading />}
      {pool.error && <ErrorBox message={pool.error} />}
      {pool.data && (
        <>
          <PoolHeading pool={pool.data} title={t("Courses of {{pool}}", { pool: pool.data.name })} />
          <p className="mb-4 mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-300">
            {t(
              "Whoever opens Ausleihbar from an active course may see and book this pool. Switching a course off keeps its members, so switching it on again restores their access.",
            )}
          </p>
          {error && <ErrorBox message={error} />}
          {courses === null && !error && <Loading />}
          {courses !== null && courses.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-200">
              <p className="font-medium text-slate-900 dark:text-slate-100">{t("No course linked yet.")}</p>
              <p className="mt-1 max-w-prose">
                {t(
                  "To link a course, open Ausleihbar from the course in your LMS (Stud.IP, Moodle, ILIAS …) as a teacher and choose this pool. Students who then open Ausleihbar from that course may see and book it.",
                )}
              </p>
            </div>
          )}
          {courses !== null && courses.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
                  <tr>
                    <th className="px-3 py-2">{t("Course")}</th>
                    <th className="px-3 py-2">{t("Platform")}</th>
                    <th className="px-3 py-2 text-right">{t("Members")}</th>
                    <th className="px-3 py-2">{t("Linked on")}</th>
                    <th className="px-3 py-2">{t("Active")}</th>
                    <th className="px-3 py-2">
                      <span className="sr-only">{t("Actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {courses.map((c) => {
                    const title = c.title || c.context_id;
                    return (
                      <tr key={c.id} className="border-t border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2 align-top font-medium text-slate-900 dark:text-slate-100">
                          {title}
                          {c.created_by && (
                            <span className="block text-xs font-normal text-slate-600 dark:text-slate-300">
                              {t("linked by {{name}}", { name: c.created_by.name })}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top text-slate-700 dark:text-slate-200">{c.platform.name}</td>
                        <td className="px-3 py-2 text-right align-top tabular-nums text-slate-700 dark:text-slate-200">
                          {c.member_count}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 align-top text-slate-700 dark:text-slate-200">
                          {formatDate(c.created_at)}
                        </td>
                        <td className="px-3 py-2 align-top">
                          <Switch
                            checked={c.is_active}
                            disabled={busyId === c.id}
                            onChange={(next) => void toggle(c, next)}
                            ariaLabel={t("{{name}} active", { name: title })}
                          />
                        </td>
                        <td className="px-3 py-2 text-right align-top">
                          <DeleteButton
                            disabled={busyId === c.id}
                            label={t("Remove {{name}}", { name: title })}
                            onClick={() => void remove(c)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Frame>
  );
}

/** Settings of one pool from the lending area (`/manage/pools/:id/settings`):
 *  the owner of a personal pool edits the fields allowed to owners; admins
 *  get the full pool form. */
export function ManagePoolSettingsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const poolId = Number(useParams().id);
  const [version, setVersion] = useState(0);
  const pool = useFetch<ResourcePool>(() => api.getManagePool(poolId), [poolId, version]);

  if (user && !user.is_lender && !user.is_staff) return <NotAuthorized />;

  return (
    <Frame>
      {pool.loading && <Loading />}
      {pool.error && <ErrorBox message={pool.error} />}
      {pool.data && !pool.data.can_edit_settings && <NotAuthorized />}
      {pool.data && pool.data.can_edit_settings && (
        <>
          <PoolHeading pool={pool.data} title={t("Settings of {{pool}}", { pool: pool.data.name })} />
          <div className="mt-3">
            <PoolForm
              key={pool.data.id}
              initial={toPoolInput(pool.data)}
              poolId={pool.data.id}
              accessGroups={pool.data.access_groups ?? []}
              ownerMode={!user?.is_staff}
              personal={pool.data.is_personal}
              onClose={() => navigate("/manage/pools")}
              onPoolPersisted={() => undefined}
              onSaved={() => {
                toast.success(t("Saved."));
                setVersion((v) => v + 1);
              }}
            />
          </div>
        </>
      )}
    </Frame>
  );
}
