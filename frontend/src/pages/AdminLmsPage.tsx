// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useState } from "react";
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { FormActionBar, sameFormValue } from "../components/FormActionBar";
import { Switch } from "../components/Switch";
import type { LtiPlatform, LtiPlatformInput, LtiSetting, LtiToolInfo, Paginated } from "../types";

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

const chipClass = "inline-block rounded-full px-2 py-0.5 text-xs font-medium";

/** Admin "LMS-Plattformen": LTI 1.3 tool endpoints for the LMS
 *  registration, the registered platforms and the switch that lets
 *  lecturers create their own pool from a course launch. */
export function AdminLmsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />
      <div className="space-y-5">
        <LtiSettingSection />
        <ToolInfoSection />
        <PlatformsSection />
      </div>
    </div>
  );
}

const sectionClass = "rounded-xl border border-slate-200 p-4 dark:border-slate-800";
const headingClass = "text-sm font-semibold text-slate-900 dark:text-slate-100";
const leadClass = "mb-4 mt-1 text-sm text-slate-600 dark:text-slate-300";

function LtiSettingSection() {
  const { t } = useTranslation();
  const toast = useToast();
  const setting = useFetch<LtiSetting>(() => api.getLtiSetting(), []);
  const [value, setValue] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (setting.data) setValue(setting.data.instructors_create_pools);
  }, [setting.data]);

  async function change(next: boolean) {
    setBusy(true);
    try {
      const saved = await api.updateLtiSetting({ instructors_create_pools: next });
      setValue(saved.instructors_create_pools);
      toast.success(t("Saved."));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={sectionClass}>
      <h2 className={headingClass}>{t("Lecturers' own pools")}</h2>
      <p className={leadClass}>
        {t(
          "When on, lecturers may create their own pool when they open Ausleihbar from an LMS course, and manage its settings and items themselves. When off, an admin creates the pool and makes the lecturer its lender; lecturers then only link their courses.",
        )}
      </p>
      {setting.error && <ErrorBox message={setting.error} />}
      {value !== null && (
        <Switch
          checked={value}
          disabled={busy}
          onChange={(next) => void change(next)}
          label={t("Lecturers may create their own pools")}
        />
      )}
    </section>
  );
}

function ToolInfoSection() {
  const { t } = useTranslation();
  const info = useFetch<LtiToolInfo>(() => api.getLtiToolInfo(), []);

  return (
    <section className={sectionClass}>
      <h2 className={headingClass}>{t("Tool endpoints")}</h2>
      <p className={leadClass}>{t("Enter these values in the tool registration of your LMS (LTI 1.3).")}</p>
      {info.loading && <Loading />}
      {info.error && <ErrorBox message={info.error} />}
      {info.data && (
        <div className="grid max-w-3xl gap-3">
          <CopyField label={t("Initiate login URL")} value={info.data.login_url} />
          <CopyField label={t("Launch / redirect URL")} value={info.data.launch_url} />
          <CopyField label={t("Keyset URL (JWKS)")} value={info.data.jwks_url} />
          <CopyField label={t("Public key")} value={info.data.public_key} multiline />
        </div>
      )}
    </section>
  );
}

/** A read-only value with a copy button. */
function CopyField({ label, value, multiline = false }: { label: string; value: string; multiline?: boolean }) {
  const { t } = useTranslation();
  const toast = useToast();
  const id = useId();

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("Copied to the clipboard."));
    } catch {
      toast.error(t("Could not copy — select the text and copy it by hand."));
    }
  }

  const fieldClass = `${inputClass} font-mono text-xs`;
  return (
    <div>
      <label htmlFor={id} className="block text-xs text-slate-600 dark:text-slate-300">
        {label}
      </label>
      <div className="mt-1 flex items-start gap-2">
        {multiline ? (
          <textarea
            id={id}
            readOnly
            rows={6}
            value={value}
            onFocus={(e) => e.target.select()}
            className={fieldClass}
          />
        ) : (
          <input id={id} readOnly value={value} onFocus={(e) => e.target.select()} className={fieldClass} />
        )}
        <button
          type="button"
          onClick={() => void copy()}
          title={t("Copy {{label}}", { label })}
          aria-label={t("Copy {{label}}", { label })}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          <Copy aria-hidden className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function PlatformsSection() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<LtiPlatform | "new" | null>(null);
  const platforms = useFetch<Paginated<LtiPlatform>>(() => api.listLtiPlatforms(), [version]);
  const refetch = () => setVersion((v) => v + 1);

  async function remove(platform: LtiPlatform) {
    if (
      !(await confirm({
        message: t(
          "Delete the platform “{{name}}”? Its linked courses and their course groups are deleted too; course members lose access to the pools.",
          { name: platform.name },
        ),
        confirmLabel: t("Delete"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteLtiPlatform(platform.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  async function toggleActive(platform: LtiPlatform, next: boolean) {
    try {
      await api.updateLtiPlatform(platform.id, { is_active: next });
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Save failed."));
    }
  }

  const rows = platforms.data?.results ?? [];

  return (
    <section className={sectionClass}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className={headingClass}>{t("LMS platforms")}</h2>
          <p className={leadClass}>{t("The LMS instances (e.g. Stud.IP, Moodle, ILIAS) that may open Ausleihbar from a course.")}</p>
        </div>
        {editing === null && (
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="shrink-0 rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
          >
            {t("+ New platform")}
          </button>
        )}
      </div>

      {editing !== null && (
        <PlatformForm
          platform={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {platforms.loading && <Loading />}
      {platforms.error && <ErrorBox message={platforms.error} />}
      {platforms.data && editing === null && (
        rows.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">{t("No platforms registered yet.")}</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {rows.map((p) => (
              <li key={p.id} className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-slate-900 dark:text-slate-100">{p.name}</span>
                  <span className="ml-2 break-all font-mono text-xs text-slate-500 dark:text-slate-400">{p.issuer}</span>
                  <div className="mt-0.5 flex flex-wrap gap-1.5">
                    <span
                      className={`${chipClass} ${
                        p.is_active
                          ? "bg-green-50 text-green-800 dark:bg-green-950/40 dark:text-green-300"
                          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      }`}
                    >
                      {p.is_active ? t("Active") : t("Inactive")}
                    </span>
                    {p.link_by_email && (
                      <span className={`${chipClass} bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200`}>
                        {t("Links accounts by email")}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:shrink-0">
                  <Switch
                    checked={p.is_active}
                    onChange={(next) => void toggleActive(p, next)}
                    ariaLabel={t("{{name}} active", { name: p.name })}
                  />
                  <EditButton onClick={() => setEditing(p)} />
                  <DeleteButton onClick={() => void remove(p)} />
                </div>
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  );
}

function toForm(p: LtiPlatform | null): LtiPlatformInput & { deployment_ids_text: string } {
  return {
    name: p?.name ?? "",
    issuer: p?.issuer ?? "",
    client_id: p?.client_id ?? "",
    auth_login_url: p?.auth_login_url ?? "",
    auth_token_url: p?.auth_token_url ?? "",
    key_set_url: p?.key_set_url ?? "",
    deployment_ids: p?.deployment_ids ?? [],
    deployment_ids_text: (p?.deployment_ids ?? []).join(", "),
    // Opt-in: e-mail linking makes the LMS the authority for account matching.
    link_by_email: p?.link_by_email ?? false,
    is_active: p?.is_active ?? true,
  };
}

function PlatformForm({
  platform,
  onClose,
  onSaved,
}: {
  platform: LtiPlatform | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [initial] = useState(() => toForm(platform));
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { deployment_ids_text, ...rest } = form;
    const data: LtiPlatformInput = {
      ...rest,
      deployment_ids: deployment_ids_text
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      if (platform) await api.updateLtiPlatform(platform.id, data);
      else await api.createLtiPlatform(data);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  const text = (key: "name" | "issuer" | "client_id" | "auth_login_url" | "auth_token_url" | "key_set_url", label: string, type = "text") => (
    <label className="block text-xs text-slate-600 dark:text-slate-300">
      {label}
      <input
        required
        type={type}
        value={form[key]}
        onChange={(e) => set(key, e.target.value)}
        className={`mt-1 ${inputClass}`}
      />
    </label>
  );

  return (
    <form onSubmit={submit} className="mb-4 space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {platform ? t("Edit {{name}}", { name: platform.name }) : t("New platform")}
      </h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {text("name", t("Name"))}
        {text("client_id", t("Client ID"))}
      </div>
      {text("issuer", t("Issuer"))}
      {text("auth_login_url", t("Authentication request URL"), "url")}
      {text("auth_token_url", t("Access token URL"), "url")}
      {text("key_set_url", t("Platform keyset URL"), "url")}
      <label className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Deployment IDs (comma-separated)")}
        <input
          value={form.deployment_ids_text}
          onChange={(e) => set("deployment_ids_text", e.target.value)}
          className={`mt-1 ${inputClass}`}
        />
      </label>
      <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={form.link_by_email}
          onChange={(e) => set("link_by_email", e.target.checked)}
        />
        <span>
          {t("Link accounts by email")}
          <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-300">
            {t(
              "A launch is matched to an existing account with the same email address — the LMS becomes the authority for that match. Enable only for a trusted LMS.",
            )}
          </span>
        </span>
      </label>
      <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
        {t("Active")}
      </label>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      )}
      <FormActionBar saving={busy} onCancel={onClose} dirty={!sameFormValue(form, initial)} />
    </form>
  );
}
