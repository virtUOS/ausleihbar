// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { useConfirm } from "../components/ConfirmDialog";
import type { WelcomeSetting } from "../types";

export function AdminWelcomePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }
  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Welcome page")}</h2>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t(
          "Shown to visitors who are not signed in. Markdown is supported. The lending locations (pools) with their images are listed automatically below this text.",
        )}
      </p>
      <WelcomeEditor />
      <LogoEditor />
    </div>
  );
}

function LogoEditor() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const setting = useFetch<WelcomeSetting>(() => api.getWelcomeSetting(), []);
  const [logo, setLogo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (setting.data) setLogo(setting.data.logo);
  }, [setting.data]);

  async function pick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.uploadShopLogo(file);
      setLogo(res.logo);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Failed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (
      !(await confirm({
        message: t("Delete the shop logo?"),
        confirmLabel: t("Delete"),
        danger: true,
      }))
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteShopLogo();
      setLogo(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8">
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Shop logo")}</h2>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        {t("Shown in the shop header. PNG, JPG or SVG.")}
      </p>
      <div className="flex items-center gap-4">
        <div className="flex h-16 w-40 items-center justify-center overflow-hidden rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2">
          {logo ? (
            <img src={logo} alt={t("Shop logo")} className="max-h-full max-w-full object-contain" />
          ) : (
            <span className="text-xs text-slate-400 dark:text-slate-400">{t("No logo")}</span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
            className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
          >
            {logo ? t("Change logo") : t("Upload logo")}
          </button>
          {logo && (
            <button
              type="button"
              disabled={busy}
              onClick={remove}
              className="rounded-full border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              {t("Remove")}
            </button>
          )}
        </div>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept="image/*,.svg"
        onChange={pick}
        className="hidden"
      />
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-300">{error}</p>}
    </div>
  );
}

function WelcomeEditor() {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const setting = useFetch<WelcomeSetting>(() => api.getWelcomeSetting(), []);
  useEffect(() => {
    if (setting.data) setText(setting.data.text);
  }, [setting.data]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await api.updateWelcomeSetting({ text });
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Failed.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="block text-xs text-slate-500 dark:text-slate-400">
          {t("Welcome text (Markdown)")}
          <textarea
            rows={12}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("## Welcome\nPlease sign in to browse and book equipment.")}
            className="mt-1 block w-full rounded-md border border-slate-300 dark:border-slate-600 dark:bg-slate-800 px-3 py-2 font-mono text-sm text-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
          />
        </label>
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {t("Preview")}
          <div className="prose prose-slate dark:prose-invert mt-1 max-w-none rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 text-slate-700 dark:text-slate-300 prose-headings:text-slate-900 dark:prose-headings:text-slate-100">
            {text.trim() ? (
              <ReactMarkdown>{text}</ReactMarkdown>
            ) : (
              <p className="text-slate-400 dark:text-slate-400">{t("Nothing yet.")}</p>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Loading…") : t("Save")}
        </button>
        {message && (
          <span className={`text-sm ${message.ok ? "text-green-700 dark:text-green-300" : "text-red-600 dark:text-red-300"}`}>
            {message.text}
          </span>
        )}
      </div>
    </form>
  );
}
