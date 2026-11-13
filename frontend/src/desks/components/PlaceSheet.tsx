// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Hand } from "lucide-react";
import { formatTime } from "../../dates";
import { BottomSheet } from "../../components/BottomSheet";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { berlinNow } from "../time";
import { pad2 } from "../weekdays";
import { AdminReservationActions } from "./AdminReservationActions";
import { FavoriteToggle } from "./FavoriteToggle";
import { stateLabel, stateMeta, StatePill } from "./placeStates";
import type { DepartmentDay, ManageReservation, OverviewFloor, OverviewPlace } from "../types";

const pad = (h: number) => `${pad2(h)}:00`;

export function PlaceSheet({
  data,
  place,
  floor,
  hour,
  adminRow,
  favorite,
  onClose,
  onChanged,
}: {
  data: DepartmentDay;
  place: OverviewPlace;
  floor: OverviewFloor;
  hour: number | null;
  /** Department admins: the selected reservation, when they may act on it. */
  adminRow?: ManageReservation | null;
  /** The viewer's favourite flag for this place and its toggle. */
  favorite?: { active: boolean; onToggle: () => void };
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [showName, setShowName] = useState(false);
  const [busy, setBusy] = useState(false);
  const entry = hour !== null ? place.hours.find((h) => h.hour === hour) : undefined;
  const state = entry?.state ?? "closed";
  const room = floor.rooms.find((r) => r.id === place.room_id)?.name;
  const meeting = data.meeting_rooms.find((m) => m.id === place.id);
  const stretch = meeting?.reservations.find((r) => hour !== null && r.start_hour <= hour && hour < r.end_hour);
  const today = berlinNow();
  const bookable = state === "free" && hour !== null && (data.day > today.date || (data.day === today.date && hour >= today.hour));
  const releasable =
    !!entry?.reservation_id && !entry.mine && (state === "booked" || state === "potentially_free");

  function book() {
    const q = new URLSearchParams({
      place: String(place.id),
      kind: place.kind,
      day: data.day,
      start: String(hour),
      end: String(hour! + 1),
    });
    navigate(`/desks/book?${q}`);
  }

  async function sendRelease() {
    setBusy(true);
    try {
      await desksApi.requestRelease(entry!.reservation_id!, showName);
      toast.success(t("Release request sent."));
      onClose();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const ownFixed = !!entry?.mine && !entry.reservation_id;
  const holder = entry?.mine ? t("Your reservation") : entry?.holder;
  const btn =
    "inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold disabled:opacity-50";
  return (
    <BottomSheet open title={place.name} onClose={onClose}>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {[floor.building, floor.name, room].filter(Boolean).join(" · ")}
        {place.kind === "meeting_room" && place.capacity
          ? ` · ${t("{{count}} seats", { count: place.capacity })}`
          : ""}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatePill state={state} />
        {hour !== null && (
          <span className="text-sm text-slate-700 dark:text-slate-200">
            {t("at {{time}}", { time: pad(hour) })}
          </span>
        )}
        {favorite && (
          <span className="ml-auto">
            <FavoriteToggle name={place.name} active={favorite.active} onToggle={favorite.onToggle} />
          </span>
        )}
      </div>
      {entry && state !== "free" && state !== "closed" && (
        <p className="mt-3 text-sm text-slate-800 dark:text-slate-100">
          {ownFixed
            ? t("Your fixed desk")
            : t("Booked by {{name}}", { name: holder ?? t("Person (hidden)") })}
        </p>
      )}
      {place.now?.until && state !== "closed" && data.day === today.date && hour === today.hour && (
        <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
          {state === "free" ? t("Free until {{time}}", { time: formatTime(place.now.until as string) }) : t("Until {{time}}", { time: formatTime(place.now.until as string) })}
        </p>
      )}
      {stretch?.comment && (
        <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{stretch.comment}</p>
      )}
      {place.fixed && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("Fixed desk")}</p>
      )}

      {/* The whole day of this place. */}
      <ul aria-label={t("Day")} className="mt-4 flex flex-wrap gap-1.5">
        {place.hours.map((h) => (
          <li
            key={h.hour}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${stateMeta(h.state).pill}`}
            title={`${pad(h.hour)} ${stateLabel(t, h.state)}`}
          >
            <span aria-hidden className="font-bold">{stateMeta(h.state).glyph}</span>
            <span>{h.hour}</span>
            <span className="sr-only">{`${pad(h.hour)} ${stateLabel(t, h.state)}`}</span>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap gap-2">
        {bookable && (
          <button type="button" onClick={book} className={`${btn} bg-brand-400 font-bold text-slate-900 hover:bg-brand-500`}>
            {t("Book")}
          </button>
        )}
        {releasable && (
          <button
            type="button"
            aria-expanded={asking}
            onClick={() => setAsking(!asking)}
            className={`${btn} border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
          >
            <Hand aria-hidden className="h-4 w-4" />
            {t("Ask to release")}
          </button>
        )}
        {entry?.mine && !ownFixed && (
          <Link
            to="/desks/mine"
            className={`${btn} border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
          >
            {t("My reservations")}
          </Link>
        )}
      </div>
      {adminRow && !entry?.mine && (
        <div className="mt-4 border-t border-slate-200 pt-3 dark:border-slate-700">
          <p className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
            {t("Administration")}
          </p>
          <AdminReservationActions
            reservation={adminRow}
            onChanged={() => {
              onClose();
              onChanged();
            }}
          />
        </div>
      )}
      {asking && releasable && (
        <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
          <label className="flex min-h-[44px] items-center gap-2 text-sm text-slate-800 dark:text-slate-100">
            <input
              type="checkbox"
              checked={showName}
              onChange={(e) => setShowName(e.target.checked)}
              className="h-5 w-5 accent-brand-600"
            />
            {t("Show my name")}
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={sendRelease}
            className={`${btn} mt-2 bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900`}
          >
            {t("Send request")}
          </button>
        </div>
      )}
    </BottomSheet>
  );
}

