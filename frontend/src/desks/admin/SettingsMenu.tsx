// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2, Layers, LayoutGrid } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { KebabMenu, type KebabItem } from "../../components/KebabMenu";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { BuildingDialog } from "../components/BuildingDialog";
import type { BuildingOption } from "../components/BuildingSelect";
import { secondaryBtn } from "../components/formStyles";
import type { Building, Floor } from "../types";
import { FloorForm } from "./LocationBar";

type Dialog = "building" | "floor" | null;

/**
 * The "+ Einstellung" menu of the places workspace: new building, new floor
 * (app admins; in the chosen building) and a link to create a department
 * (app admins). Equipment and the place name pattern live in the settings tab.
 */
export function SettingsMenu({
  appAdmin,
  buildings,
  buildingId,
  floors,
  onBuildingCreated,
  onFloorCreated,
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
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  const items: KebabItem[] = [
    { label: t("New building"), icon: Building2, onClick: () => setDialog("building") },
    ...(appAdmin ? [{ label: t("New floor"), icon: Layers, onClick: () => setDialog("floor") }] : []),
    ...(appAdmin
      ? [{ label: t("Create a new department"), icon: LayoutGrid, onClick: () => navigate("/admin/pools") }]
      : []),
  ];

  return (
    <>
      <KebabMenu
        items={items}
        trigger={{ label: t("Setting"), glyph: "+", chevron: true, className: secondaryBtn }}
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
    </>
  );
}
