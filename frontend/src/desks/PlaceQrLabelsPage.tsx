// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Printer } from "lucide-react";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { FORMATS, printStylesheet, type LabelFormat } from "../components/qrLabelFormats";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "./components/formStyles";
import type { Place } from "./types";

interface Labelled {
  place: Place;
  where: string;
}

/** One printable place label: QR sticker (`<shop>/desks/q/<token>`) + name. */
function PlaceLabel({ item, format }: { item: Labelled; format: LabelFormat }) {
  const [src, setSrc] = useState<string | null>(null);
  const placeId = item.place.id;
  const token = item.place.qr_token;
  useEffect(() => {
    let url: string | null = null;
    let alive = true;
    desksApi
      .placeQr(placeId)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        if (alive) setSrc(url);
        else URL.revokeObjectURL(url);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
    // The token changes when the code is regenerated.
  }, [placeId, token]);

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
        <p className="truncate text-xs font-semibold text-slate-900 dark:text-slate-100">
          {item.place.name}
        </p>
        <p className="truncate text-[10px] text-slate-600 dark:text-slate-300">{item.where}</p>
      </div>
    </div>
  );
}

/** Printable QR labels of a department's places (same print layout as the
 *  lending desk's item labels). `?place=<id>` preselects a single place. */
export function PlaceQrLabelsPage() {
  const { pool, isAdmin } = useDesks();
  if (!isAdmin) return <Navigate to="/desks" replace />;
  return <QrLabels key={pool} pool={pool} />;
}

function QrLabels({ pool }: { pool: number }) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const only = Number(params.get("place")) || null;
  const [formatId, setFormatId] = useState(FORMATS[0].id);
  const [skip, setSkip] = useState<Set<number>>(new Set());
  const { data, error } = useFetch(
    async () => {
      const [floors, rooms, places] = await Promise.all([
        desksApi.floors(),
        desksApi.rooms(),
        desksApi.places(),
      ]);
      const roomMap = new Map(rooms.map((r) => [r.id, r]));
      const floorMap = new Map(floors.map((f) => [f.id, f]));
      const out: Labelled[] = [];
      for (const place of places) {
        const room = roomMap.get(place.room);
        const floor = room ? floorMap.get(room.floor) : undefined;
        if (!room || !floor || floor.pool !== pool) continue;
        out.push({
          place,
          where: [floor.building, floor.name, room.name].filter(Boolean).join(" · "),
        });
      }
      return out.sort((a, b) => a.where.localeCompare(b.where) || a.place.name.localeCompare(b.place.name));
    },
    [pool],
  );
  const format = FORMATS.find((f) => f.id === formatId) ?? FORMATS[0];
  const items = useMemo(
    () => (data ?? []).filter((i) => (only ? i.place.id === only : true)),
    [data, only],
  );
  useEffect(() => setSkip(new Set()), [pool, only]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;

  const selected = items.filter((i) => !skip.has(i.place.id));
  const toggle = (id: number) =>
    setSkip((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div>
      <link rel="stylesheet" href={printStylesheet(format)} />
      <div className="print:hidden">
        <Link
          to="/desks/manage/places"
          className="mb-3 inline-flex min-h-[44px] items-center gap-2 text-sm font-semibold text-slate-700 hover:underline dark:text-slate-200"
        >
          <ArrowLeft aria-hidden className="h-4 w-4" />
          {t("Back to places")}
        </Link>
        <h2 className="mb-1 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("QR labels of places")}
        </h2>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Each code opens the place in Ausleihbar: scanning it checks you in or books the place.")}
        </p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
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
            disabled={selected.length === 0}
            className={primaryBtn}
          >
            <Printer aria-hidden className="h-4 w-4" />
            {t("Print {{count}} label", { count: selected.length })}
          </button>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">{t("No places in this department.")}</p>
        ) : (
          <>
            <div className="mb-2 flex items-center gap-3 text-sm">
              <span className="text-slate-600 dark:text-slate-300">
                {t("{{selected}} of {{total}} selected", { selected: selected.length, total: items.length })}
              </span>
              <button type="button" onClick={() => setSkip(new Set())} className={secondaryBtn + " !min-h-[44px]"}>
                {t("Select all")}
              </button>
              <button
                type="button"
                onClick={() => setSkip(new Set(items.map((i) => i.place.id)))}
                className={secondaryBtn}
              >
                {t("Select none")}
              </button>
            </div>
            <div className="mb-4 max-h-56 overflow-y-auto rounded-md border border-slate-200 p-1 dark:border-slate-800">
              {items.map((i) => (
                <label
                  key={i.place.id}
                  className="flex min-h-[44px] items-center gap-3 px-2 text-sm text-slate-700 dark:text-slate-200"
                >
                  <input
                    type="checkbox"
                    className="h-5 w-5"
                    checked={!skip.has(i.place.id)}
                    onChange={() => toggle(i.place.id)}
                  />
                  <span className="font-medium text-slate-900 dark:text-slate-100">{i.place.name}</span>
                  <span className="truncate text-xs text-slate-600 dark:text-slate-300">{i.where}</span>
                </label>
              ))}
            </div>
          </>
        )}
      </div>
      <div className="label-sheet flex flex-wrap gap-2">
        {selected.map((i) => (
          <PlaceLabel key={i.place.id} item={i} format={format} />
        ))}
      </div>
    </div>
  );
}
