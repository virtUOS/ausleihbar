// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
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
import { StatePill, stateLabel } from "./placeStates";
import {
  PlaceTimeline,
  meetingRoomEntry,
  placeEntry,
  type TimelineBlock,
  type TimelineBooking,
} from "./PlaceTimeline";
import type { DepartmentDay, ManageReservation, OverviewFloor, OverviewPlace } from "../types";

const pad = (h: number) => `${pad2(h)}:00`;

/** Details of a place for a day: its timeline (free hours can be selected
 *  and booked), and for a booking clicked in it who holds it, a release
 *  request and — for department admins — move / cancel. */
export function PlaceSheet({
  data,
  place,
  floor,
  focusHour,
  manageable,
  booking,
  favorite,
  onClose,
  onChanged,
}: {
  data: DepartmentDay;
  place: OverviewPlace;
  floor: OverviewFloor;
  /** Hour whose booking is shown first (e.g. the block clicked in the list). */
  focusHour: number | null;
  /** Department admins: the day's reservations they may act on. */
  manageable: ManageReservation[];
  booking?: TimelineBooking;
  /** The viewer's favourite flag for this place and its toggle. */
  favorite?: { active: boolean; onToggle: () => void };
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [showName, setShowName] = useState(false);
  const [busy, setBusy] = useState(false);
  const today = berlinNow();
  const room = floor.rooms.find((r) => r.id === place.room_id)?.name;
  const meeting = data.meeting_rooms.find((m) => m.id === place.id);
  const timeline = meeting ? { ...meetingRoomEntry(meeting, ""), capacity: place.capacity } : placeEntry(place);

  const blockAt = (h: number | null) =>
    h === null ? null : (timeline.blocks.find((b) => b.start_hour <= h && h < b.end_hour) ?? null);
  const [focus, setFocus] = useState<TimelineBlock | null>(() => blockAt(focusHour));
  // After a reload the block may have changed: look it up again by its hour.
  const block = focus ? blockAt(focus.start_hour) : null;
  const entry = block ? place.hours.find((h) => h.hour === block.start_hour) : undefined;
  const ownFixed = !!block?.mine && !entry?.reservation_id;
  const releasable =
    !!entry?.reservation_id && !entry.mine && (block?.state === "booked" || block?.state === "potentially_free");
  const adminRow =
    entry?.reservation_id && !entry.mine
      ? (manageable.find((r) => r.id === entry.reservation_id) ?? null)
      : null;
  const holder = block?.holder;

  async function sendRelease() {
    if (!entry?.reservation_id) return;
    setBusy(true);
    try {
      await desksApi.requestRelease(entry.reservation_id, showName);
      toast.success(t("Release request sent."));
      onClose();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const btn =
    "inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold disabled:opacity-50";
  const isToday = data.day === today.date;
  return (
    <BottomSheet open title={place.name} onClose={onClose}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-sm text-slate-600 dark:text-slate-300">
          {[floor.building, floor.name, room].filter(Boolean).join(" · ")}
          {place.kind === "meeting_room" && place.capacity
            ? ` · ${t("{{count}} seats", { count: place.capacity })}`
            : ""}
        </p>
        {favorite && (
          <FavoriteToggle name={place.name} active={favorite.active} onToggle={favorite.onToggle} />
        )}
      </div>
      {isToday && place.now && place.now.state !== "closed" && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <StatePill state={place.now.state} />
          {place.now.until &&
            (place.now.state === "free"
              ? t("Free until {{time}}", { time: formatTime(place.now.until) })
              : t("Until {{time}}", { time: formatTime(place.now.until) }))}
        </p>
      )}
      {place.fixed && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("Fixed desk")}</p>
      )}

      {/* The whole day: select free hours to book, click a booking for details. */}
      <div className="mt-3">
        <PlaceTimeline
          entry={timeline}
          open={data.open_hours}
          booking={booking}
          bare
          onBlockClick={(b) => {
            setAsking(false);
            setFocus((cur) => (cur && cur.key === b.key ? null : b));
          }}
          focusKey={block?.key ?? null}
        />
      </div>

      {block && (
        <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
          <p className="flex flex-wrap items-center gap-2 text-sm text-slate-800 dark:text-slate-100">
            <span className="font-semibold">
              {pad(block.start_hour)}–{pad(block.end_hour)}
            </span>
            <span>
              {ownFixed
                ? t("Your fixed desk")
                : block.mine
                  ? t("Your reservation")
                  : t("Booked by {{name}}", { name: holder ?? t("Person (hidden)") })}
            </span>
            {block.state !== "booked" && (
              <span className="text-slate-600 dark:text-slate-300">({stateLabel(t, block.state)})</span>
            )}
          </p>
          {block.comment && (
            <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{block.comment}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
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
            {block.mine && !ownFixed && (
              <Link
                to="/desks/mine"
                className={`${btn} border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
              >
                {t("My reservations")}
              </Link>
            )}
          </div>
          {asking && releasable && (
            <div className="mt-3">
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
          {adminRow && (
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
        </div>
      )}
    </BottomSheet>
  );
}
