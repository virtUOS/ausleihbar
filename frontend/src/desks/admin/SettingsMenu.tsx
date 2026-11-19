// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { Building2, Layers, LayoutGrid, Plus, Sparkles, Type } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { KebabMenu, type KebabItem } from "../../components/KebabMenu";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { BuildingDialog } from "../components/BuildingDialog";
import type { BuildingOption } from "../components/BuildingSelect";
import { primaryBtn, secondaryBtn } from "../components/formStyles";
import type { Building, DeskAdminSetting, Floor } from "../types";
import { FeatureDialog } from "./FeatureDialog";
import { FloorForm } from "./LocationBar";

type Dialog = "building" | "floor" | "feature" | "pattern" | null;

/**
 * The "+ Einstellung" menu of the places workspace: new building, new floor
 * (app admins; in the chosen building), new equipment, the campus-wide place
 * name pattern (app admins) and a link to create a department (app admins).
 */
export function SettingsMenu({
  appAdmin,
  buildings,
  buildingId,
  floors,
  onBuildingCreated,
  onFloorCreated,
  onFeatureCreated,
}: {
  appAdmin: boolean;
  /** Building choices for a new floor. */
  buildings: BuildingOption[];
  /** The chosen building (preselected for a new floor). */
  buildingId: number | null | undefined;
  /** All floors (a new floor goes after the last one of its building). */
  floors: Floor[];
  onBuildingCreated: (building: Building) => void;
  onFloorCreated: (floor: Floor) => void;
  onFeatureCreated: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  const items: KebabItem[] = [
    { label: t("New building"), icon: Building2, onClick: () => setDialog("building") },
    ...(appAdmin ? [{ label: t("New floor"), icon: Layers, onClick: () => setDialog("floor") }] : []),
    { label: t("New equipment"), icon: Sparkles, onClick: () => setDialog("feature") },
    ...(appAdmin
      ? [
          { label: t("Place name pattern"), icon: Type, onClick: () => setDialog("pattern") },
          { label: t("Create a new department"), icon: LayoutGrid, onClick: () => navigate("/admin/pools") },
        ]
      : []),
  ];

  return (
    <>
      <KebabMenu
        items={items}
        trigger={{ label: t("Setting"), icon: Plus, className: secondaryBtn }}
      />
      <BuildingDialog
        open={dialog === "building"}
        savedMessage={
          appAdmin
            ? undefined
            : `${t("Building saved.")} ${t("The building appears here once it has a floor of your department.")}`
        }
        onClose={close}
        onSaved={(b) => {
          close();
          onBuildingCreated(b);
        }}
      />
      <BottomSheet open={dialog === "floor"} title={t("New floor")} onClose={close}>
        <FloorForm
          floor={null}
          buildings={buildings}
          buildingId={buildingId ?? null}
          onCancel={close}
          onSave={async (v) => {
            const position =
              Math.max(-1, ...floors.filter((f) => f.building === v.building).map((f) => f.position)) + 1;
            try {
              const floor = await desksApi.createFloor({ ...v, position });
              toast.success(t("Floor saved."));
              close();
              onFloorCreated(floor);
            } catch (e) {
              toast.error(e instanceof Error ? e.message : t("The request failed."));
            }
          }}
        />
      </BottomSheet>
      <FeatureDialog open={dialog === "feature"} appAdmin={appAdmin} onClose={close} onSaved={onFeatureCreated} />
      <BottomSheet open={dialog === "pattern"} title={t("Place name pattern")} onClose={close}>
        <NamePatternForm onDone={close} />
      </BottomSheet>
    </>
  );
}

/** How new place names continue a room's name: letters ("15/201 A") or numbers ("15/201-1"). */
function NamePatternForm({ onDone }: { onDone: () => void }) {
  const setting = useFetch(() => desksApi.adminSetting(), []);
  if (setting.error) return <ErrorBox message={setting.error} />;
  if (!setting.data) return <Loading />;
  return <NamePatternFields initial={setting.data.place_name_pattern} onDone={onDone} />;
}

function NamePatternFields({
  initial,
  onDone,
}: {
  initial: DeskAdminSetting["place_name_pattern"];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const [pattern, setPattern] = useState(initial);
  const [busy, setBusy] = useState(false);
  const example = pattern === "letter" ? "15/201 A, 15/201 B, 15/201 C" : "15/201-1, 15/201-2, 15/201-3";
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await desksApi.saveAdminSetting({ place_name_pattern: pattern });
          toast.success(t("Name pattern saved."));
          onDone();
        } catch (err) {
          toast.error(err instanceof Error ? err.message : t("The request failed."));
        } finally {
          setBusy(false);
        }
      }}
      className="flex flex-col gap-4"
    >
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {t("New places continue the room's name. The pattern applies to the whole campus.")}
      </p>
      <SegmentedControl
        size="md"
        ariaLabel={t("Place name pattern")}
        value={pattern}
        onChange={(v) => setPattern(v)}
        options={[
          { value: "letter" as const, label: t("Letters") },
          { value: "number" as const, label: t("Numbers") },
        ]}
        className="w-full sm:w-max"
      />
      <p className="text-sm text-slate-800 dark:text-slate-200">
        {t("Example: {{names}}", { names: example })}
      </p>
      <FormButtons onCancel={onDone} disabled={busy} />
    </form>
  );
}

function FormButtons({ onCancel, disabled }: { onCancel: () => void; disabled: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="mt-1 flex flex-wrap gap-2">
      <button type="submit" disabled={disabled} className={primaryBtn}>
        {t("Save")}
      </button>
      <button type="button" onClick={onCancel} className={secondaryBtn}>
        {t("Cancel")}
      </button>
    </div>
  );
}
