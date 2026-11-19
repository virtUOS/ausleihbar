// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { BottomSheet } from "../../components/BottomSheet";
import { WarningNotice } from "../../components/WarningNotice";
import { desksApi } from "../api";
import { inputCls, labelCls, primaryBtn, secondaryBtn } from "../components/formStyles";
import { NameField, hasDefaultName } from "../components/NameField";
import type { BatchResult, Floor, RoomKind } from "../types";
import { BatchPreview, FieldError, errorOf, fieldErrors } from "./batchPreview";

type Mode = "single" | "range";

/** Add rooms to a floor (app admins): one room by name, or a numbered range
 *  (prefix + from..to) that is previewed first; names that exist are skipped. */
export function AddRoomsDialog({
  open,
  floor,
  pools,
  onClose,
  onCreated,
}: {
  open: boolean;
  floor: Floor;
  /** Active departments by pool id (the department choice). */
  pools: Map<number, string>;
  onClose: () => void;
  onCreated: (count: number, skipped: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <BottomSheet open={open} title={t("Add rooms")} onClose={onClose}>
      {open && <AddRoomsForm floor={floor} pools={pools} onClose={onClose} onCreated={onCreated} />}
    </BottomSheet>
  );
}

function AddRoomsForm({
  floor,
  pools,
  onClose,
  onCreated,
}: {
  floor: Floor;
  pools: Map<number, string>;
  onClose: () => void;
  onCreated: (count: number, skipped: number) => void;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("range");
  const [nameDe, setNameDe] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [prefix, setPrefix] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [pool, setPool] = useState<number | "">("");
  const [kind, setKind] = useState<RoomKind>("office");
  const [preview, setPreview] = useState<{ key: string; result: BatchResult } | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Any change of the range invalidates the preview.
  const key = JSON.stringify([prefix, start, end, pool, kind]);
  const current = preview?.key === key ? preview.result : null;
  const range = mode === "range";
  const filled = range ? start.trim() !== "" && end.trim() !== "" : hasDefaultName(nameDe, nameEn);
  const body = { floor: floor.id, prefix, start: start.trim(), end: end.trim(), pool: pool === "" ? null : pool, kind };
  const poolOptions = [...pools.entries()].sort((a, b) => a[1].localeCompare(b[1]));

  function failed(e: unknown) {
    const { fields: f, general: g } = fieldErrors(e);
    setFields(f);
    setGeneral(g);
  }

  async function runPreview() {
    if (busy) return;
    setBusy(true);
    setFields({});
    setGeneral(null);
    try {
      setPreview({ key, result: await desksApi.batchRooms({ ...body, dry_run: true }) });
    } catch (e) {
      setPreview(null);
      failed(e);
    }
    setBusy(false);
  }

  async function create() {
    if (busy) return;
    setBusy(true);
    setFields({});
    setGeneral(null);
    try {
      if (range) {
        const result = await desksApi.batchRooms({ ...body, dry_run: false });
        onCreated(result.created.length, result.skipped.length);
      } else {
        await desksApi.createRoom({
          floor: floor.id,
          pool: pool === "" ? null : pool,
          name_de: nameDe.trim(),
          name_en: nameEn.trim() || null,
          kind,
        });
        onCreated(1, 0);
      }
    } catch (e) {
      failed(e);
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (range ? current && current.created.length > 0 : filled) void create();
      }}
      className="flex flex-col gap-4"
    >
      <SegmentedControl
        size="md"
        ariaLabel={t("How many rooms")}
        value={mode}
        onChange={(v) => {
          setMode(v);
          setFields({});
          setGeneral(null);
        }}
        options={[
          { value: "range" as const, label: t("Several rooms") },
          { value: "single" as const, label: t("One room") },
        ]}
        className="w-full sm:w-max"
      />
      {range ? (
        <>
          <div>
            <label htmlFor="rooms-prefix" className={labelCls}>{t("Name prefix")}</label>
            <input
              id="rooms-prefix"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              placeholder={t("e.g. Room ")}
              aria-describedby="rooms-prefix-error"
              className={inputCls}
            />
            <FieldError id="rooms-prefix-error" message={errorOf(fields, "prefix")} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="rooms-start" className={labelCls}>{t("From")}</label>
              <input
                id="rooms-start"
                inputMode="numeric"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                aria-invalid={!!errorOf(fields, "start")}
                aria-describedby="rooms-start-error"
                className={inputCls}
              />
              <FieldError id="rooms-start-error" message={errorOf(fields, "start")} />
            </div>
            <div>
              <label htmlFor="rooms-end" className={labelCls}>{t("To")}</label>
              <input
                id="rooms-end"
                inputMode="numeric"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                aria-invalid={!!errorOf(fields, "end")}
                aria-describedby="rooms-end-error"
                className={inputCls}
              />
              <FieldError id="rooms-end-error" message={errorOf(fields, "end")} />
            </div>
          </div>
        </>
      ) : (
        <div>
          <NameField de={nameDe} en={nameEn} onChange={(l, v) => (l === "de" ? setNameDe(v) : setNameEn(v))} />
          <FieldError id="rooms-name-error" message={errorOf(fields, "name", "name_de", "name_en")} />
        </div>
      )}
      <SegmentedControl
        size="md"
        ariaLabel={t("Kind")}
        value={kind}
        onChange={setKind}
        options={[
          { value: "office" as const, label: t("Office") },
          { value: "meeting" as const, label: t("Meeting room area") },
        ]}
        className="w-full sm:w-max"
      />
      <div>
        <label htmlFor="rooms-pool" className={labelCls}>{t("Department (optional)")}</label>
        <select
          id="rooms-pool"
          value={pool}
          onChange={(e) => setPool(e.target.value === "" ? "" : Number(e.target.value))}
          aria-describedby="rooms-pool-error"
          className={inputCls}
        >
          <option value="">{t("No department")}</option>
          {poolOptions.map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
        <FieldError id="rooms-pool-error" message={errorOf(fields, "pool")} />
      </div>
      <FieldError id="rooms-floor-error" message={errorOf(fields, "floor", "dry_run")} />
      {range && current && <BatchPreview result={current} />}
      {general && <WarningNotice message={general} />}
      <div className="flex flex-wrap gap-2">
        {range && (
          <button type="button" onClick={runPreview} disabled={busy || !filled} className={secondaryBtn}>
            {t("Preview")}
          </button>
        )}
        <button
          type="submit"
          disabled={busy || !filled || (range && !(current && current.created.length > 0))}
          className={primaryBtn}
        >
          {t("Create")}
        </button>
        <button type="button" onClick={onClose} className={secondaryBtn}>{t("Cancel")}</button>
      </div>
    </form>
  );
}
