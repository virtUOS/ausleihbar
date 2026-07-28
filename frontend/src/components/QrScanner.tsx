// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";

/**
 * QR input with two modes: the device camera (smartphone at the desk) and a
 * manual text field — so it works with or without a camera / over plain HTTP.
 * Calls `onScan` with the raw decoded text; the caller parses it.
 */
export function QrScanner({
  onScan,
  manualPlaceholder = i18n.t("Enter code…"),
  autoStart = false,
}: {
  onScan: (text: string) => void;
  manualPlaceholder?: string;
  /** Turn the camera on as soon as the scanner mounts (requests permission;
   *  the browser remembers the grant per origin on HTTPS). */
  autoStart?: boolean;
}) {
  const { t } = useTranslation();
  const [active, setActive] = useState(autoStart);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const [elementId] = useState(
    () => `qr-${Math.random().toString(36).slice(2)}`,
  );
  // Keep the latest onScan without restarting the camera each render.
  const onScanRef = useRef(onScan);
  onScanRef.current = onScan;
  const last = useRef<{ text: string; at: number }>({ text: "", at: 0 });

  useEffect(() => {
    if (!active) return;
    const scanner = new Html5Qrcode(elementId);
    let cancelled = false;
    // Resolves once start() has settled (ok or failed), so cleanup can wait for
    // it before stopping. `started` tells cleanup whether a stop() is needed.
    let started = false;
    const startP = scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        (text) => {
          const now = Date.now();
          // Ignore repeated reads of the same code held in front of the camera.
          if (text === last.current.text && now - last.current.at < 1500) return;
          last.current = { text, at: now };
          onScanRef.current(text);
        },
        () => {},
      )
      .then(() => {
        started = true;
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message ?? t("Camera unavailable."));
      });
    return () => {
      cancelled = true;
      // Defer stop() into a promise callback and guard it: calling stop() before
      // start() has finished (React StrictMode's mount→cleanup→mount) throws
      // synchronously in html5-qrcode, which — thrown from a cleanup — would
      // crash the whole tree. Waiting + swallowing keeps it contained.
      startP
        .then(() => (started ? scanner.stop() : undefined))
        .catch(() => {})
        .finally(() => {
          try {
            scanner.clear();
          } catch {
            /* not rendered / already cleared */
          }
        });
    };
  }, [active, elementId, t]);

  function submitManual(event: React.FormEvent) {
    event.preventDefault();
    const value = manual.trim();
    if (!value) return;
    onScan(value);
    setManual("");
  }

  return (
    <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{t("Scan")}</span>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setActive((a) => !a);
          }}
          className={`rounded-full px-3 py-1.5 text-sm font-medium ${
            active
              ? "bg-slate-900 text-white"
              : "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          }`}
        >
          {active ? t("Stop camera") : t("Use camera")}
        </button>
      </div>

      {active && (
        <div className="mt-3">
          <div id={elementId} className="mx-auto w-full max-w-xs overflow-hidden rounded-lg" />
          {error && <p className="mt-2 text-sm text-red-600 dark:text-red-300">{error}</p>}
        </div>
      )}

      <form onSubmit={submitManual} className="mt-3 flex gap-2">
        <input
          value={manual}
          onChange={(e) => setManual(e.target.value)}
          placeholder={manualPlaceholder}
          className="block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
        />
        <button
          type="submit"
          disabled={!manual.trim()}
          className="rounded-full border border-slate-300 px-4 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {t("Enter")}
        </button>
      </form>
    </div>
  );
}
