// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronLeft, Monitor } from "lucide-react";
import { useAuth } from "../auth";
import i18n from "../i18n";
import { ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { FloorPlanEditor, type PlanTemplate } from "./components/FloorPlanEditor";
import type { Floor, Place, Room } from "./types";

interface Data {
  floor: Floor;
  rooms: Room[];
  places: Place[];
}

/** Loads a template blob into an object URL with its natural size (the plan
 *  units). The image comes from an authenticated fetch: a plain `<image href>`
 *  to the API would lack the session on a cross-origin dev setup. */
async function loadTemplate(floorId: number): Promise<PlanTemplate> {
  const blob = await desksApi.floorTemplate(floorId);
  const url = URL.createObjectURL(blob);
  try {
    // `onload`, not `decode()`: decode can stall while the tab is hidden.
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error(i18n.t("The template image could not be loaded.")));
      el.src = url;
    });
    return { url, width: img.naturalWidth, height: img.naturalHeight };
  } catch (e) {
    URL.revokeObjectURL(url);
    throw e;
  }
}

/** `/desks/manage/plans/:floorId`: the floor-plan editor (department admins,
 *  desktop-first; phones get a notice). Data is loaded once per floor — not
 *  via `useFetch`, whose refetch on a language switch would drop edits. */
export function FloorPlanEditorPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const { floorId } = useParams();
  const id = Number(floorId);
  const { isAdmin } = useDesks();
  const { user } = useAuth();
  const adminPools = user?.desk_admin_pool_ids ?? [];
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [template, setTemplate] = useState<PlanTemplate | null>(null);
  const [templateReady, setTemplateReady] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!Number.isInteger(id)) return;
    let cancelled = false;
    (async () => {
      try {
        const [floor, rooms, places] = await Promise.all([
          desksApi.floor(id),
          desksApi.rooms(),
          desksApi.places(),
        ]);
        const floorRooms = rooms.filter((r) => r.floor === floor.id);
        const roomIds = new Set(floorRooms.map((r) => r.id));
        const tpl = floor.has_template ? await loadTemplate(floor.id).catch(() => null) : null;
        if (cancelled) {
          if (tpl) URL.revokeObjectURL(tpl.url);
          return;
        }
        setData({ floor, rooms: floorRooms, places: places.filter((p) => roomIds.has(p.room)) });
        setTemplate(tpl);
        setTemplateReady(true);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : t("The request failed."));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Release the template's object URL when it is replaced or on leave.
  useEffect(() => () => {
    if (template) URL.revokeObjectURL(template.url);
  }, [template]);

  async function upload(file: File) {
    if (!data) return;
    setUploading(true);
    try {
      await desksApi.uploadFloorTemplate(data.floor.id, file);
      const next = await loadTemplate(data.floor.id);
      setTemplate(next);
      toast.success(t("Template uploaded."));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setUploading(false);
    }
  }

  if (!Number.isInteger(id)) return <Navigate to="/desks/manage/places" replace />;
  // Before the floor is known, the current department decides; afterwards
  // the floor's own department — switching the department picker must not
  // unmount the editor (and drop unsaved edits).
  if (!data && !isAdmin) return <Navigate to="/desks" replace />;
  if (error) return <ErrorBox message={error} />;
  if (!data || !templateReady) return <Loading />;
  if (!adminPools.includes(data.floor.pool)) return <Navigate to="/desks/manage/places" replace />;

  const title = `${data.floor.building ? `${data.floor.building} · ` : ""}${data.floor.name}`;

  return (
    <section aria-labelledby="plan-editor-title">
      <Link
        to="/desks/manage/places"
        className="mb-2 inline-flex min-h-[44px] items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
      >
        <ChevronLeft aria-hidden className="h-4 w-4" />
        {t("Places")}
      </Link>
      <h2 id="plan-editor-title" className="mb-3 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Edit floor plan: {{floor}}", { floor: title })}
      </h2>
      <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 md:hidden dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
        <Monitor aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-brand-700 dark:text-brand-400" />
        <p>{t("The plan editor needs a larger screen. Please open this page on a computer or tablet.")}</p>
      </div>
      <div className="hidden md:block">
        <FloorPlanEditor
          key={data.floor.id}
          floor={data.floor}
          rooms={data.rooms}
          places={data.places}
          template={template}
          uploading={uploading}
          onUploadTemplate={(file) => void upload(file)}
        />
      </div>
    </section>
  );
}
