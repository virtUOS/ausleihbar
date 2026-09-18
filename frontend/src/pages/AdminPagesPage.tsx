// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { ReorderControls } from "../components/ReorderControls";
import { TranslatableField } from "@basicbar/ui";
import { useReorder } from "../useReorder";
import { getDefaultContentLang } from "@basicbar/ui";
import type { CmsPage, CmsPageInput, Paginated } from "../types";

/** Built-in pages that live alongside the CMS content pages but have their own
 *  dedicated editors (reached at /admin/pages/<key>). Not deletable. */
const BUILTIN_PAGES = [
  {
    key: "welcome",
    title: "Welcome page",
    description: "Greeting text & logo shown to signed-out visitors.",
  },
  {
    key: "shop",
    title: "Shop start page",
    description: "Suggestion rows shown to signed-in users.",
  },
] as const;

const EMPTY: CmsPageInput = {
  slug: "",
  title_de: "",
  title_en: "",
  body_de: "",
  body_en: "",
  is_published: true,
  show_in_footer: true,
};

function toInput(p: CmsPage): CmsPageInput {
  return {
    slug: p.slug,
    title_de: p.title_de ?? "",
    title_en: p.title_en ?? "",
    body_de: p.body_de ?? "",
    body_en: p.body_en ?? "",
    is_published: p.is_published,
    show_in_footer: p.show_in_footer,
  };
}

export function AdminPagesPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<CmsPage | "new" | null>(null);
  const [reordering, setReordering] = useState(false);
  const pages = useFetch<Paginated<CmsPage>>(() => api.listPages(), [version]);
  const rows = pages.data?.results ?? [];
  const reorder = useReorder(rows, api.reorderPages);
  const displayRows = reordering ? reorder.order : rows;

  if (user && !user.is_staff) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">
        {t("Not authorized.")}
      </div>
    );
  }

  const refetch = () => setVersion((v) => v + 1);

  async function remove(page: CmsPage) {
    if (
      !(await confirm({
        message: t("Delete page “{{title}}”?", { title: page.title }),
        confirmLabel: t("Delete"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deletePage(page.id);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Administration")}
      </h1>
      <AdminTabs />

      <div className="mb-1 mt-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {t("Pages")}
        </h2>
        {editing === null && (
          <div className="flex gap-2">
            {rows.length > 1 && (
              <button
                type="button"
                onClick={() => setReordering((r) => !r)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                  reordering
                    ? "bg-slate-900 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                {reordering ? t("Done") : t("Reorder")}
              </button>
            )}
            {!reordering && (
              <button
                type="button"
                onClick={() => setEditing("new")}
                className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("+ New page")}
              </button>
            )}
          </div>
        )}
      </div>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {reordering
          ? t(
              "Drag rows to reorder, or use the ↑ / ↓ buttons — this sets the footer link order. New pages are added at the end. Changes are saved automatically.",
            )
          : t(
              "Content pages written in Markdown (e.g. imprint, privacy). Published pages flagged for the footer appear as footer links.",
            )}
      </p>

      {editing !== null && (
        <PageForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          pageId={editing === "new" ? null : editing.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {pages.loading && <Loading />}
      {pages.error && <ErrorBox message={pages.error} />}

      {pages.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("Title")}</th>
                <th className="px-3 py-2">{t("Status")}</th>
                <th className="px-3 py-2 text-right">{reordering ? t("Order") : ""}</th>
              </tr>
            </thead>
            <tbody>
              {!reordering &&
                BUILTIN_PAGES.map((b) => (
                <tr key={b.key} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {t(b.title)}
                    </span>
                    <span className="block text-xs text-slate-400 dark:text-slate-500">
                      {t(b.description)}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone="slate">{t("Built-in")}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-0.5">
                      <EditButton onClick={() => navigate(`/admin/pages/${b.key}`)} />
                    </div>
                  </td>
                </tr>
              ))}
              {displayRows.map((p, i) => (
                <tr
                  key={p.id}
                  draggable={reordering}
                  onDragStart={reordering ? () => reorder.onDragStart(p.id) : undefined}
                  onDragEnter={reordering ? () => reorder.onDragEnter(p.id) : undefined}
                  onDragOver={reordering ? (e) => e.preventDefault() : undefined}
                  onDrop={reordering ? reorder.onDrop : undefined}
                  className={`border-t border-slate-100 dark:border-slate-800 ${
                    reordering ? "cursor-grab bg-white dark:bg-slate-900" : ""
                  }`}
                >
                  <td className="px-3 py-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {p.title}
                    </span>
                    <span className="text-slate-400 dark:text-slate-500"> /{p.slug}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap gap-1">
                      {p.is_published ? (
                        <Badge tone="green">{t("Published")}</Badge>
                      ) : (
                        <Badge tone="slate">{t("Draft")}</Badge>
                      )}
                      {p.is_published && p.show_in_footer && (
                        <Badge tone="brand">{t("Footer")}</Badge>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {reordering ? (
                      <div className="flex justify-end">
                        <ReorderControls
                          label={p.title}
                          isFirst={i === 0}
                          isLast={i === displayRows.length - 1}
                          onUp={() => reorder.move(p.id, -1)}
                          onDown={() => reorder.move(p.id, 1)}
                        />
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-0.5">
                        <EditButton onClick={() => setEditing(p)} />
                        <DeleteButton onClick={() => remove(p)} />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td
                    colSpan={3}
                    className="px-3 py-6 text-center text-slate-500 dark:text-slate-400"
                  >
                    {t("No pages yet.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Badge({
  tone,
  children,
}: {
  tone: "green" | "slate" | "brand";
  children: React.ReactNode;
}) {
  const tones = {
    green:
      "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
    slate: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    brand: "bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function PageForm({
  initial,
  pageId,
  onClose,
  onSaved,
}: {
  initial: CmsPageInput;
  pageId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<CmsPageInput>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  // Auto-fill the slug from the title only while creating a fresh page and the
  // admin hasn't typed a slug yet — never silently rewrite an existing URL.
  const [slugTouched, setSlugTouched] = useState(pageId !== null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (pageId === null) await api.createPage(form);
      else await api.updatePage(pageId, form);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mb-5 space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {pageId === null ? t("New page") : t("Edit {{title}}", { title: initial.title_de })}
      </h3>

      <div className="grid gap-4 sm:grid-cols-2">
        <TranslatableField
          label={t("Title")}
          required
          values={{ de: form.title_de, en: form.title_en }}
          onChange={(lang, v) =>
            setForm((f) => ({
              ...f,
              [`title_${lang}`]: v,
              // The slug follows the canonical-language title until edited.
              slug:
                lang === getDefaultContentLang() && !slugTouched
                  ? slugify(v)
                  : f.slug,
            }))
          }
          inputClass={inputClass}
        />
        <label className="block text-xs text-slate-500 dark:text-slate-400">
          {t("URL slug")}
          <input
            required
            value={form.slug}
            onChange={(e) => {
              setSlugTouched(true);
              setForm((f) => ({ ...f, slug: e.target.value }));
            }}
            className={`mt-1 font-mono ${inputClass}`}
          />
          <span className="mt-1 block text-slate-400 dark:text-slate-500">
            /pages/{form.slug || "…"}
          </span>
        </label>
      </div>

      <TranslatableField
        label={t("Body (Markdown)")}
        values={{ de: form.body_de, en: form.body_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`body_${lang}`]: v }))}
        inputClass={inputClass}
        renderInput={({ value, onChange, id }) => (
          <div>
            <div className="mb-1 flex justify-end">
              <button
                type="button"
                onClick={() => setShowPreview((p) => !p)}
                className="text-xs font-medium text-slate-600 underline-offset-2 hover:underline dark:text-slate-300"
              >
                {showPreview ? t("Edit") : t("Preview")}
              </button>
            </div>
            {showPreview ? (
              <div className="prose prose-slate min-h-[12rem] max-w-none rounded-md border border-slate-200 p-3 text-sm dark:prose-invert dark:border-slate-700">
                <ReactMarkdown>{value || t("Nothing to preview yet.")}</ReactMarkdown>
              </div>
            ) : (
              <textarea
                id={id}
                rows={14}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                className={`font-mono ${inputClass}`}
              />
            )}
          </div>
        )}
      />

      <div className="flex flex-wrap items-end gap-4">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <input
            type="checkbox"
            checked={form.is_published}
            onChange={(e) => setForm((f) => ({ ...f, is_published: e.target.checked }))}
            className="h-4 w-4 rounded border-slate-300 text-brand-500 focus:ring-brand-400"
          />
          {t("Published")}
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <input
            type="checkbox"
            checked={form.show_in_footer}
            onChange={(e) => setForm((f) => ({ ...f, show_in_footer: e.target.checked }))}
            className="h-4 w-4 rounded border-slate-300 text-brand-500 focus:ring-brand-400"
          />
          {t("Show in footer")}
        </label>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Saving…") : t("Save")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
