// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Pencil, RefreshCw, Trash2 } from "lucide-react";
import { useAuth } from "../auth";
import i18n from "../i18n";
import { useFetch } from "../useFetch";
import { BottomSheet } from "../components/BottomSheet";
import { useConfirm } from "../components/ConfirmDialog";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { dangerBtn, inputCls, labelCls, primaryBtn, secondaryBtn, sectionTitleCls } from "./components/formStyles";
import type { DoorDisplay, DoorPanel, Floor, Room } from "./types";

const PANELS: DoorPanel[] = ["2.1", "5.79"];
/** A display that was not seen for this long is flagged (it wakes up far more often). */
const STALE_MS = 30 * 60 * 1000;

/** "3 minutes ago" in the UI language. */
function relativeTime(iso: string, now: number): string {
  const diffSec = Math.round((new Date(iso).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(i18n.language, { numeric: "auto" });
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(0, "second");
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  return rtf.format(Math.round(diffSec / 86400), "day");
}

interface RoomChoice {
  id: number;
  label: string;
}

/** Rooms as "Building Floor · Room" choices, sorted by that label. */
function roomChoices(rooms: Room[], floors: Floor[]): RoomChoice[] {
  const floorMap = new Map(floors.map((f) => [f.id, f]));
  return rooms
    .map((r) => {
      const f = floorMap.get(r.floor);
      const where = [f?.building_code, f?.name].filter(Boolean).join(" ");
      return { id: r.id, label: where ? `${where} · ${r.name}` : r.name };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

function RoomSelect({
  id,
  value,
  choices,
  onChange,
}: {
  id: string;
  value: number | null;
  choices: RoomChoice[];
  onChange: (id: number | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <select
      id={id}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      className={inputCls}
    >
      <option value="">{t("Choose a room")}</option>
      {choices.map((c) => (
        <option key={c.id} value={c.id}>
          {c.label}
        </option>
      ))}
    </select>
  );
}

/** Loads an image through the API (session cookie) as an object URL. */
function useBlobUrl(load: () => Promise<Blob>, deps: unknown[]): { url: string | null; failed: boolean } {
  const [state, setState] = useState<{ url: string | null; failed: boolean }>({ url: null, failed: false });
  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    setState((s) => ({ ...s, failed: false }));
    load()
      .then((blob) => {
        created = URL.createObjectURL(blob);
        if (cancelled) URL.revokeObjectURL(created);
        else setState({ url: created, failed: false });
      })
      .catch(() => {
        if (!cancelled) setState({ url: null, failed: true });
      });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** Preview image (1-bit PNG, scaled with crisp pixels); click enlarges. */
function Preview({
  load,
  deps,
  alt,
  enlargeable = true,
}: {
  load: () => Promise<Blob>;
  deps: unknown[];
  alt: string;
  enlargeable?: boolean;
}) {
  const { t } = useTranslation();
  const { url, failed } = useBlobUrl(load, deps);
  const [big, setBig] = useState(false);
  if (failed) return <p className="text-xs text-slate-500 dark:text-slate-300">{t("Preview not available.")}</p>;
  if (!url) return <div className="h-16 w-28 animate-pulse rounded bg-slate-200 dark:bg-slate-700" aria-hidden />;
  const img = (cls: string) => (
    <img src={url} alt={alt} className={`${cls} border border-slate-300 bg-white dark:border-slate-600`} style={{ imageRendering: "pixelated" }} />
  );
  if (!enlargeable) return img("max-w-full");
  return (
    <>
      <button type="button" onClick={() => setBig(true)} className="block rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500" aria-label={t("Enlarge preview")}>
        {img("max-h-24 w-auto")}
      </button>
      <BottomSheet open={big} title={alt} onClose={() => setBig(false)}>
        {img("w-full")}
      </BottomSheet>
    </>
  );
}

/** Door displays of a department (department admins): pair with the code the
 *  device shows, rename / move / revoke, see last contact and battery, and
 *  preview any room's sign without hardware. */
export function DisplaysPage() {
  const { pool, isAdmin } = useDesks();
  const { user } = useAuth();
  if (!isAdmin || !(user?.desk_admin_pool_ids ?? []).includes(pool)) return <Navigate to="/desks" replace />;
  return <Displays key={pool} pool={pool} />;
}

function Displays({ pool }: { pool: number }) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirm = useConfirm();
  const [reload, setReload] = useState(0);
  // Bumped by "Refresh": reloads the list and every preview image.
  const [stamp, setStamp] = useState(0);
  const [pairing, setPairing] = useState(false);
  const [editing, setEditing] = useState<DoorDisplay | null>(null);
  const { data, error } = useFetch(
    async () => {
      const [displays, rooms, floors] = await Promise.all([desksApi.displays(pool), desksApi.rooms(), desksApi.floors()]);
      return { displays, choices: roomChoices(rooms, floors) };
    },
    [pool, reload],
  );

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const { displays, choices } = data;
  const now = Date.now();

  async function revoke(d: DoorDisplay) {
    const ok = await confirm({
      title: t("Remove door display"),
      message: t("Remove door display? The device shows a pairing code again afterwards."),
      confirmLabel: t("Remove"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.deleteDisplay(d.id);
      toast.success(t("Door display removed."));
      setReload((n) => n + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className={sectionTitleCls}>{t("Door displays")}</h2>
          <p className="max-w-prose text-sm text-slate-600 dark:text-slate-300">
            {t("E-ink signs at room doors show the room's current state. A new sign shows a pairing code: enter it here and choose its room.")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={secondaryBtn}
            onClick={() => {
              setStamp((n) => n + 1);
              setReload((n) => n + 1);
            }}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            {t("Refresh")}
          </button>
          <button type="button" className={primaryBtn} onClick={() => setPairing(true)}>
            {t("Pair display")}
          </button>
        </div>
      </div>

      {displays.length === 0 ? (
        <Empty label={t("No door displays paired yet.")} />
      ) : (
        <ul className="flex flex-col gap-3">
          {displays.map((d) => {
            const stale = !d.last_seen_at || now - new Date(d.last_seen_at).getTime() > STALE_MS;
            const where = [d.room.building, d.room.floor].filter(Boolean).join(" ");
            return (
              <li key={d.id} className="flex flex-wrap items-start gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                <Preview
                  load={() => desksApi.displayPreviewUrl(d.id)}
                  deps={[d.id, d.room.id, stamp]}
                  alt={t("Preview of {{name}}", { name: d.name })}
                />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-900 dark:text-slate-100">{d.name}</p>
                  <p className="text-sm text-slate-600 dark:text-slate-300">
                    {where ? `${where} · ${d.room.name}` : d.room.name}
                  </p>
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm text-slate-700 dark:text-slate-200">
                    <dt className="text-slate-500 dark:text-slate-300">{t("Panel")}</dt>
                    <dd>{d.panel}″</dd>
                    <dt className="text-slate-500 dark:text-slate-300">{t("Last contact")}</dt>
                    <dd className="flex flex-wrap items-center gap-2">
                      {d.last_seen_at ? relativeTime(d.last_seen_at, now) : t("never")}
                      {stale && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                          {t("No recent contact")}
                        </span>
                      )}
                    </dd>
                    <dt className="text-slate-500 dark:text-slate-300">{t("Battery")}</dt>
                    <dd>{d.battery_mv == null ? "—" : `${(d.battery_mv / 1000).toFixed(1)} V`}</dd>
                    <dt className="text-slate-500 dark:text-slate-300">{t("Firmware")}</dt>
                    <dd>{d.firmware || "—"}</dd>
                  </dl>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={secondaryBtn} onClick={() => setEditing(d)}>
                    <Pencil className="h-4 w-4" aria-hidden />
                    {t("Edit")}
                  </button>
                  <button type="button" className={dangerBtn} onClick={() => void revoke(d)}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                    {t("Remove")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <RoomPreviewSection choices={choices} />

      <BottomSheet open={pairing} title={t("Pair display")} onClose={() => setPairing(false)}>
        <PairForm
          choices={choices}
          onClose={() => setPairing(false)}
          onDone={() => {
            setPairing(false);
            setReload((n) => n + 1);
          }}
        />
      </BottomSheet>
      <BottomSheet open={!!editing} title={t("Edit door display")} onClose={() => setEditing(null)}>
        {editing && (
          <EditForm
            key={editing.id}
            display={editing}
            choices={choices}
            onClose={() => setEditing(null)}
            onDone={() => {
              setEditing(null);
              setReload((n) => n + 1);
            }}
          />
        )}
      </BottomSheet>
    </div>
  );
}

function PairForm({ choices, onClose, onDone }: { choices: RoomChoice[]; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [code, setCode] = useState("");
  const [room, setRoom] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  // The backend normalises case, spaces and dashes; 8 characters are needed.
  const normalized = code.replace(/[\s-]/g, "");
  const valid = normalized.length === 8 && room !== null;

  async function submit() {
    if (!valid || room === null) return;
    setBusy(true);
    try {
      await desksApi.claimDisplay({ code: normalized, room, name: name.trim() || undefined });
      toast.success(t("Door display paired."));
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="flex flex-col gap-4">
        <div>
          <label htmlFor="display-code" className={labelCls}>{t("Pairing code")}</label>
          <input
            id="display-code"
            required
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={12}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="XXXX-XXXX"
            className={`${inputCls} font-mono uppercase tracking-widest`}
            aria-describedby="display-code-hint"
          />
          <p id="display-code-hint" className="mt-1 text-xs text-slate-500 dark:text-slate-300">
            {t("The 8-character code shown on the display (XXXX-XXXX).")}
          </p>
        </div>
        <div>
          <label htmlFor="display-room" className={labelCls}>{t("Room")}</label>
          <RoomSelect id="display-room" value={room} choices={choices} onChange={setRoom} />
        </div>
        <div>
          <label htmlFor="display-name" className={labelCls}>{t("Name (optional)")}</label>
          <input id="display-name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !valid} className={primaryBtn}>{t("Pair display")}</button>
        <button type="button" onClick={onClose} className={secondaryBtn}>{t("Cancel")}</button>
      </div>
    </form>
  );
}

function EditForm({ display, choices, onClose, onDone }: { display: DoorDisplay; choices: RoomChoice[]; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [name, setName] = useState(display.name);
  const [room, setRoom] = useState<number | null>(display.room.id);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (room === null) return;
    setBusy(true);
    try {
      const changes: { name?: string; room?: number } = {};
      if (name.trim() && name.trim() !== display.name) changes.name = name.trim();
      if (room !== display.room.id) changes.room = room;
      if (Object.keys(changes).length) await desksApi.updateDisplay(display.id, changes);
      toast.success(t("Door display saved."));
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="flex flex-col gap-4">
        <div>
          <label htmlFor="edit-display-name" className={labelCls}>{t("Name")}</label>
          <input id="edit-display-name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label htmlFor="edit-display-room" className={labelCls}>{t("Room")}</label>
          <RoomSelect id="edit-display-room" value={room} choices={choices} onChange={setRoom} />
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="submit" disabled={busy || room === null || !name.trim()} className={primaryBtn}>{t("Save")}</button>
        <button type="button" onClick={onClose} className={secondaryBtn}>{t("Cancel")}</button>
      </div>
    </form>
  );
}

/** Preview of a room's sign for a panel size, no hardware needed. */
function RoomPreviewSection({ choices }: { choices: RoomChoice[] }) {
  const { t } = useTranslation();
  const [room, setRoom] = useState<number | null>(null);
  const [panel, setPanel] = useState<DoorPanel>("5.79");
  return (
    <section className="mt-8" aria-labelledby="room-preview-title">
      <h3 id="room-preview-title" className={sectionTitleCls}>{t("Preview without a device")}</h3>
      <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
        {t("Shows how a room's sign looks on a display size.")}
      </p>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 sm:max-w-sm">
          <label htmlFor="preview-room" className={labelCls}>{t("Room")}</label>
          <RoomSelect id="preview-room" value={room} choices={choices} onChange={setRoom} />
        </div>
        <div>
          <label htmlFor="preview-panel" className={labelCls}>{t("Panel")}</label>
          <select id="preview-panel" value={panel} onChange={(e) => setPanel(e.target.value as DoorPanel)} className={inputCls}>
            {PANELS.map((p) => (
              <option key={p} value={p}>{p}″</option>
            ))}
          </select>
        </div>
      </div>
      {room !== null && (
        <Preview
          key={`${room}-${panel}`}
          load={() => desksApi.roomDoorPreviewUrl(room, panel)}
          deps={[room, panel]}
          alt={t("Door sign preview")}
          enlargeable={false}
        />
      )}
    </section>
  );
}
