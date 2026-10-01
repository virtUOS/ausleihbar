// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import type { ImageAction } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ListToolbar } from "../components/ListToolbar";
import { MultiSelectList } from "../components/MultiSelectList";
import { ImageCropField } from "../components/ImageCropField";
import { TranslatableField } from "@basicbar/ui";
import { ReorderControls } from "../components/ReorderControls";
import { OrderList, moveId } from "../components/OrderList";
import { symbolFor } from "../emoji";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { useReorder } from "../useReorder";
import type {
  ManageSection,
  ManageSectionInput,
  ManageSet,
  Paginated,
  ProductType,
} from "../types";

const EMPTY: ManageSectionInput = {
  title_de: "",
  title_en: "",
  description_de: "",
  description_en: "",
  image: "",
  product_types: [],
  sets: [],
};

function toInput(s: ManageSection): ManageSectionInput {
  return {
    title_de: s.title_de ?? "",
    title_en: s.title_en ?? "",
    description_de: s.description_de ?? "",
    description_en: s.description_en ?? "",
    image: s.image,
    product_types: s.product_types,
    sets: s.sets,
  };
}

export function AdminSectionsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<ManageSection | "new" | null>(null);
  const [reordering, setReordering] = useState(false);
  const [query, setQuery] = useState("");
  const sections = useFetch<Paginated<ManageSection>>(
    () => api.listManagedSections({ pageSize: 2000 }),
    [version],
  );
  const productTypes = useFetch<Paginated<ProductType>>(
    () => api.listProductTypes({ pageSize: 2000 }),
    [],
  );
  const sets = useFetch<Paginated<ManageSet>>(() => api.listSets({ pageSize: 2000 }), []);
  const rows = sections.data?.results ?? [];
  const reorder = useReorder(rows, api.reorderSections);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const filtered = query.trim()
    ? rows.filter((s) => s.title.toLowerCase().includes(query.trim().toLowerCase()))
    : rows;
  const displayRows = reordering ? reorder.order : filtered;

  const refetch = () => setVersion((v) => v + 1);

  async function remove(section: ManageSection) {
    if (
      !(await confirm({
        message: t("Move section “{{title}}” to the trash?", { title: section.title }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteSection(section.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const allTypes = productTypes.data?.results ?? [];
  const allSets = sets.data?.results ?? [];

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Sections (“Sparten”)")}</h2>
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
                {t("+ New section")}
              </button>
            )}
          </div>
        )}
      </div>

      {reordering && (
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
          {t(
            "Drag rows to reorder, or use the ↑ / ↓ buttons. New sections are always added at the end. Changes are saved automatically.",
          )}
        </p>
      )}

      {editing !== null && (
        <SectionForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          sectionId={editing === "new" ? null : editing.id}
          allTypes={allTypes}
          allSets={allSets}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {editing === null && !reordering && rows.length > 0 && (
        <ListToolbar
          search={query}
          onSearch={setQuery}
          count={filtered.length}
          hidePager
          placeholder={t("Search sections…")}
        />
      )}

      {(sections.loading || productTypes.loading || sets.loading) && <Loading />}
      {sections.error && <ErrorBox message={sections.error} />}

      {sections.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Title")}</th>
                <th className="px-3 py-2">{t("Product types")}</th>
                <th className="px-3 py-2 text-right">
                  {reordering ? t("Order") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((s, i) => (
                <tr
                  key={s.id}
                  draggable={reordering}
                  onDragStart={reordering ? () => reorder.onDragStart(s.id) : undefined}
                  onDragEnter={reordering ? () => reorder.onDragEnter(s.id) : undefined}
                  onDragOver={reordering ? (e) => e.preventDefault() : undefined}
                  onDrop={reordering ? reorder.onDrop : undefined}
                  className={`border-t border-slate-100 dark:border-slate-800 ${
                    reordering ? "cursor-grab bg-white dark:bg-slate-900" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{s.title}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{s.product_type_count}</td>
                  <td className="px-3 py-2 text-right">
                    {reordering ? (
                      <div className="flex justify-end">
                        <ReorderControls
                          label={s.title}
                          isFirst={i === 0}
                          isLast={i === displayRows.length - 1}
                          onUp={() => reorder.move(s.id, -1)}
                          onDown={() => reorder.move(s.id, 1)}
                        />
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center justify-end gap-0.5">
                          <EditButton onClick={() => setEditing(s)} />
                          <DeleteButton onClick={() => remove(s)} />
                        </div>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {displayRows.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t("No sections yet.")}
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

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function SectionForm({
  initial,
  sectionId,
  allTypes,
  allSets,
  onClose,
  onSaved,
}: {
  initial: ManageSectionInput;
  sectionId: number | null;
  allTypes: ProductType[];
  allSets: ManageSet[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ManageSectionInput>(initial);
  const [imageAction, setImageAction] = useState<ImageAction>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleType(id: number) {
    setForm((f) => ({
      ...f,
      product_types: f.product_types.includes(id)
        ? f.product_types.filter((c) => c !== id)
        : [...f.product_types, id],
    }));
  }

  function toggleSet(id: number) {
    setForm((f) => ({
      ...f,
      sets: f.sets.includes(id)
        ? f.sets.filter((s) => s !== id)
        : [...f.sets, id],
    }));
  }

  // Move an id within one of the ordered lists (delta -1 up / +1 down).
  function move(key: "product_types" | "sets", id: number, delta: number) {
    setForm((f) => ({ ...f, [key]: moveId(f[key], id, delta) }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved =
        sectionId === null
          ? await api.createSection(form)
          : await api.updateSection(sectionId, form);
      await api.applyImage("sections", saved.id, imageAction);
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
        {sectionId === null
          ? t("New section")
          : t("Edit {{title}}", { title: initial.title_de })}
      </h3>

      <TranslatableField
        label={t("Title")}
        required
        values={{ de: form.title_de, en: form.title_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`title_${lang}`]: v }))}
        inputClass={inputClass}
      />
      <TranslatableField
        label={t("Description")}
        multiline
        values={{ de: form.description_de, en: form.description_en }}
        onChange={(lang, v) =>
          setForm((f) => ({ ...f, [`description_${lang}`]: v }))
        }
        inputClass={inputClass}
      />
      <div className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Image")}
        <div className="mt-1">
          <ImageCropField
            currentUrl={form.image}
            aspect={4 / 3}
            fallback={symbolFor(form.title_de ?? "")}
            onChange={setImageAction}
          />
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Product types")}</p>
        <MultiSelectList
          options={allTypes.map((pt) => ({
            id: pt.id,
            label: pt.name,
            sublabel: t("{{count}} product", { count: pt.product_count }),
          }))}
          selected={form.product_types}
          onToggle={toggleType}
          placeholder={t("Search product types…")}
          emptyText={t("No product types available.")}
        />
        <OrderList
          label={t("Order in the section")}
          ids={form.product_types}
          labelFor={(id) => allTypes.find((pt) => pt.id === id)?.name ?? `#${id}`}
          onMove={(id, delta) => move("product_types", id, delta)}
        />
      </div>

      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">
          {t("Sets — shown in this section after the product types.")}
        </p>
        <MultiSelectList
          options={allSets.map((s) => ({
            id: s.id,
            label: `🎒 ${s.name}`,
            sublabel: t("{{count}} product", { count: s.product_count }),
          }))}
          selected={form.sets}
          onToggle={toggleSet}
          placeholder={t("Search sets…")}
          emptyText={t("No sets available.")}
        />
        <OrderList
          label={t("Order in the section")}
          ids={form.sets}
          labelFor={(id) => allSets.find((s) => s.id === id)?.name ?? `#${id}`}
          onMove={(id, delta) => move("sets", id, delta)}
        />
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
