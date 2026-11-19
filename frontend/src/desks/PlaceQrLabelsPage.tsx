// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Printer } from "lucide-react";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { FORMATS, printStylesheet, type LabelFormat } from "../components/qrLabelFormats";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { useAuth } from "../auth";
import { QrLabelPicker, labelsToPrint, useLabelQr } from "../components/QrLabelPicker";
import type { DeskPool } from "./pools";
import { inputCls, labelCls, primaryBtn } from "./components/formStyles";
import type { Place } from "./types";

interface Labelled {
  id: number;
  place: Place;
  /** Who may book it: the place's own access groups, else the department. */
  audience: string;
  /** Name, location (not printed: the sticker sits on the place) and
   *  audience, for the search. */
  search: string;
}

/** One printable place label: QR sticker (`<shop>/desks/q/<token>`) + name. */
function PlaceLabel({ item, format }: { item: Labelled; format: LabelFormat }) {
  const { t } = useTranslation();
  // The token is part of the key: regenerating the code reloads the image.
  const src = useLabelQr(`place:${item.place.id}:${item.place.qr_token}`, () =>
    desksApi.placeQr(item.place.id).then((blob) => URL.createObjectURL(blob)),
  );

  const qr = `${Math.max(format.h - 6, 16)}mm`;
  return (
    <div
      className="qr-label flex items-center gap-2 rounded-md border border-slate-300 p-1.5 dark:border-slate-600"
      style={{ width: `${format.w}mm`, height: `${format.h}mm`, breakInside: "avoid" }}
    >
      <div
        className="flex shrink-0 items-center justify-center bg-white"
        style={{ width: qr, height: qr }}
      >
        {src ? (
          <img src={src} alt="" className="h-full w-full object-contain" />
        ) : (
          <span className="text-[8px] text-slate-400 dark:text-slate-300">…</span>
        )}
      </div>
      <div className="min-w-0">
        {/* Call to action: the phone's camera app opens booking / check-in. */}
        <p className="text-[10px] font-bold uppercase leading-tight tracking-wide text-slate-900 dark:text-slate-100">
          {t("Scan to book or check in")}
        </p>
        <p className="mt-0.5 truncate text-xs font-semibold text-slate-900 dark:text-slate-100">
          {item.place.name}
        </p>
        <p className="text-[10px] leading-tight text-slate-600 dark:text-slate-300">
          {t("For {{who}}", { who: item.audience })}
        </p>
      </div>
    </div>
  );
}

/** Printable QR labels of a department's places (same print layout as the
 *  lending desk's item labels). `?place=<id>` preselects a single place. */
export function PlaceQrLabelsPage() {
  const { pool, pools, isAdmin, select } = useDesks();
  const { user } = useAuth();
  if (!isAdmin) return <Navigate to="/desks" replace />;
  const adminIds = user?.desk_admin_pool_ids ?? [];
  const adminPools = pools.filter((p) => adminIds.includes(p.id));
  return <QrLabels key={pool} pool={pool} pools={adminPools} onPool={select} />;
}

function QrLabels({ pool, pools, onPool }: { pool: number; pools: DeskPool[]; onPool: (id: number) => void }) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const only = Number(params.get("place")) || null;
  const [formatId, setFormatId] = useState(FORMATS[0].id);
  const [selected, setSelected] = useState<Set<number>>(() => new Set(only ? [only] : []));
  const [query, setQuery] = useState("");
  const poolName = pools.find((p) => p.id === pool)?.name ?? "";
  const { data, error } = useFetch(
    async () => {
      const [floors, rooms, places, groups] = await Promise.all([
        desksApi.floors(),
        desksApi.rooms(),
        desksApi.places(),
        desksApi.accessGroups(pool),
      ]);
      const groupNames = new Map(groups.map((g) => [g.id, g.name]));
      const roomMap = new Map(rooms.map((r) => [r.id, r]));
      const floorMap = new Map(floors.map((f) => [f.id, f]));
      const out: (Labelled & { where: string })[] = [];
      for (const place of places) {
        if (place.pool !== pool) continue;
        // A place assigned on its own may sit in a room the department admin
        // does not see (then without location).
        const room = roomMap.get(place.room);
        const floor = room ? floorMap.get(room.floor) : undefined;
        const where = [floor?.building_code, floor?.name, room?.name].filter(Boolean).join(" ");
        const audience =
          place.access_groups
            .map((id) => groupNames.get(id))
            .filter(Boolean)
            .join(", ") || poolName;
        out.push({ id: place.id, place, audience, where, search: `${place.name} ${where} ${audience}` });
      }
      return out.sort((a, b) => a.where.localeCompare(b.where) || a.place.name.localeCompare(b.place.name));
    },
    [pool, poolName],
  );
  const format = FORMATS.find((f) => f.id === formatId) ?? FORMATS[0];

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const printCount = labelsToPrint(data, query, selected).length;

  return (
    <div>
      <link rel="stylesheet" href={printStylesheet(format)} />
      <div className="print:hidden">
        <h2 className="mb-1 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("QR labels of places")}
        </h2>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Each code opens the place in Ausleihbar: scanning it checks you in or books the place.")}
        </p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1 sm:flex-none">
            <label htmlFor="qr-pool" className={labelCls}>
              {t("Department")}
            </label>
            <select
              id="qr-pool"
              value={pool}
              onChange={(e) => onPool(Number(e.target.value))}
              className={inputCls}
            >
              {pools.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-0 flex-1 sm:flex-none">
            <label htmlFor="qr-format" className={labelCls}>
              {t("Format")}
            </label>
            <select
              id="qr-format"
              value={formatId}
              onChange={(e) => setFormatId(e.target.value)}
              className={inputCls}
            >
              {FORMATS.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={printCount === 0}
            className={primaryBtn}
          >
            <Printer aria-hidden className="h-4 w-4" />
            {t("Print {{count}} label", { count: printCount })}
          </button>
        </div>
      </div>
      <QrLabelPicker
        items={data}
        query={query}
        onQueryChange={setQuery}
        selected={selected}
        onSelectedChange={setSelected}
        render={(item) => <PlaceLabel item={item} format={format} />}
        emptyText={t("No places in this department.")}
      />
    </div>
  );
}
