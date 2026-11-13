// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Armchair, CircleAlert, CircleCheck, Clock, DoorOpen } from "lucide-react";
import { formatTime } from "../dates";
import { useFetch } from "../useFetch";
import { Loading } from "../components/Status";
import { useBookNow } from "./bookNow";
import { desksApi } from "./api";
import { resolveTokenError, type TokenError } from "./errors";
import { TokenErrorNotice } from "./components/TokenErrorNotice";
import { useDesks } from "./DesksLayout";
import type { PlaceBrief, ScanResult } from "./types";

type Phase = { state: "loading" } | { state: "done"; result: ScanResult } | { state: "error"; error: TokenError };

const linkBtn =
  "inline-flex min-h-[44px] items-center justify-center rounded-full border border-slate-300 px-5 text-sm font-semibold text-slate-800 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-800";

function placeLine(p: PlaceBrief): string {
  return [p.building, p.floor, p.room].filter(Boolean).join(" · ");
}

/** `/desks/q/:token` — the QR sticker of a place: checks in a booked place or
 *  books a free one spontaneously, then shows one large status block. */
export function CheckInPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const [phase, setPhase] = useState<Phase>({ state: "loading" });
  const scanned = useRef<string | null>(null);

  // Scan exactly once per token (StrictMode runs effects twice in dev; a second
  // scan must never create a second booking).
  useEffect(() => {
    if (scanned.current === token) return;
    scanned.current = token;
    desksApi
      .scan(token)
      .then((result) => setPhase({ state: "done", result }))
      .catch(async (e) => setPhase({ state: "error", error: await resolveTokenError(e, t) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const reasons: Record<string, string> = {
    no_rights: t("You are not allowed to use this place."),
    inactive: t("This place is not in use."),
    closed: t("The department is closed today."),
    outside_hours: t("The department is closed at this time."),
    unknown_token: t("This QR code is not known (any more)."),
    horizon: t("This day cannot be booked yet."),
  };

  let body;
  if (phase.state === "loading") {
    body = <Loading />;
  } else if (phase.state === "error") {
    body = <TokenErrorNotice error={phase.error} />;
  } else {
    const { result } = phase;
    const res = result.reservation;
    const place = res ? [res.place.name, placeLine(res.place)].filter(Boolean).join(" · ") : "";
    if (result.action === "checked_in") {
      body = <Block tone="ok" icon={CircleCheck} title={t("Checked in")} text={place} />;
    } else if (result.action === "booked") {
      body = (
        <Block
          tone="ok"
          icon={CircleCheck}
          title={t("Booked until {{time}} and checked in", { time: formatTime(res?.end ?? result.next_free_until) })}
          text={place}
        />
      );
    } else if (result.action === "taken") {
      body = (
        <>
          <Block
            tone="warn"
            icon={Clock}
            title={
              result.next_free_until
                ? t("Occupied until {{time}}", { time: formatTime(result.next_free_until) })
                : t("Occupied")
            }
            text={t("Somebody else has this place right now.")}
          />
          <Alternatives />
        </>
      );
    } else {
      body = (
        <Block
          tone="neutral"
          icon={CircleAlert}
          title={t("Not possible")}
          text={reasons[result.reason] ?? t("This place cannot be used right now.")}
        />
      );
    }
  }

  return (
    <section aria-labelledby="checkin-title">
      <h2 id="checkin-title" className="sr-only">
        {t("Check in")}
      </h2>
      {body}
      {phase.state !== "loading" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/desks/mine" className={linkBtn}>
            {t("My reservations")}
          </Link>
          <Link to="/desks" className={linkBtn}>
            {t("Free now")}
          </Link>
        </div>
      )}
    </section>
  );
}

const TONES = {
  ok: "border-green-300 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100",
  warn: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100",
  neutral: "border-slate-300 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
};

function Block({
  tone,
  icon: Icon,
  title,
  text,
}: {
  tone: keyof typeof TONES;
  icon: typeof CircleCheck;
  title: string;
  text?: string;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  // The result replaces a spinner: move focus to it for keyboard / screen reader users.
  useEffect(() => heading.current?.focus(), []);
  return (
    <div role={tone === "ok" ? "status" : "alert"} className={`rounded-2xl border p-6 text-center ${TONES[tone]}`}>
      <Icon aria-hidden className="mx-auto mb-3 h-12 w-12" />
      <h3 ref={heading} tabIndex={-1} className="text-2xl font-bold outline-none">
        {title}
      </h3>
      {text && <p className="mt-2 text-sm">{text}</p>}
    </div>
  );
}

/** Free places of the department, bookable with one tap. */
function Alternatives() {
  const { t } = useTranslation();
  const { pool } = useDesks();
  const { booking, bookNow } = useBookNow(pool);
  const { data, error } = useFetch(() => desksApi.freeNow(pool, "desk"), [pool]);

  if (error) {
    return (
      <p className="mt-6 text-sm text-slate-600 dark:text-slate-300">
        {t("Free places could not be loaded. Try \"Free now\".")}
      </p>
    );
  }
  if (!data || data.length === 0) return null;
  return (
    <div className="mt-6">
      <h3 className="mb-2 text-base font-bold text-slate-900 dark:text-slate-100">{t("Free alternatives")}</h3>
      <ul className="space-y-2">
        {data.slice(0, 5).map((place) => {
          const Icon = place.kind === "meeting_room" ? DoorOpen : Armchair;
          return (
            <li
              key={place.id}
              className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
            >
              <Icon aria-hidden className="h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-900 dark:text-slate-100">{place.name}</p>
                <p className="truncate text-sm text-slate-600 dark:text-slate-300">
                  {[place.building, place.floor, place.room].filter(Boolean).join(" · ")}
                  {" · "}
                  {place.free_until
                    ? t("free until {{time}}", { time: formatTime(place.free_until) })
                    : t("free all day")}
                </p>
              </div>
              <button
                type="button"
                disabled={booking !== null}
                onClick={() => bookNow(place)}
                className="min-h-[44px] shrink-0 rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50"
              >
                {t("Book now")}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
