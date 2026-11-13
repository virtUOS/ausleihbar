// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// The desksharing hour grid is Europe/Berlin wall-clock time, whatever the
// browser's own time zone is.
const parts = (d: Date) => {
  const f = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Berlin",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  });
  const o: Record<string, string> = {};
  for (const p of f.formatToParts(d)) o[p.type] = p.value;
  return { date: `${o.year}-${o.month}-${o.day}`, hour: Number(o.hour) };
};

/** Today's date (ISO) and the current full hour in Berlin. */
export const berlinNow = () => parts(new Date());

/** Berlin date (ISO) and hour of an ISO timestamp. */
export const berlinParts = (iso: string) => parts(new Date(iso));
