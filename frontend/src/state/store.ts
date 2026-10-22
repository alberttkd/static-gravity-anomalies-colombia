/** UI state (Zustand). Server state lives in TanStack Query. */
import { create } from "zustand";
import type { ReductionConfig } from "../api/types";

export type Quantity =
  | "faa_mgal"
  | "sba_mgal"
  | "cba_mgal"
  | "cba_residual_mgal"
  | "height_m"
  | "sigma_cba_mgal"
  | "qc"
  | "delta_ref_mgal"
  | "delta_cba_mgal";
export type InspectorTab = "station" | "validation" | "profile" | "qc" | "density" | "provenance";
export type GridLayer = "value" | "sigma_cal" | "trend" | "residual";
export type Theme = "system" | "light" | "dark";

export const DEFAULT_REDUCTION: Partial<ReductionConfig> = {
  density_kg_m3: 2670,
  curvature: "lafehr1991_closed_form",
  honkasalo: true,
  atmospheric: true,
  height_correction: "hinze2005_second_order",
  terrain_reference_density_kg_m3: 2670,
  legacy_mode: false,
};

interface UiState {
  dataset: string;
  quantity: Quantity;
  reduction: Partial<ReductionConfig>;
  runId: string | null;
  referenceRunId: string | null;
  gridId: string | null;
  jobId: string | null;
  gridLayer: GridLayer;
  showGrid: boolean;
  showContours: boolean;
  showHatch: boolean;
  opacity: number;
  tab: InspectorTab;
  selected: string | null;
  drawing: boolean;
  profileLine: [number, number][];
  densities: [number, number];
  theme: Theme;
  set: (patch: Partial<Omit<UiState, "set">>) => void;
}

export const useUi = create<UiState>((set) => ({
  dataset: "synthetic",
  quantity: "cba_mgal",
  reduction: DEFAULT_REDUCTION,
  runId: null,
  referenceRunId: null,
  gridId: null,
  jobId: null,
  gridLayer: "value",
  showGrid: true,
  showContours: true,
  showHatch: true,
  opacity: 0.8,
  tab: "station",
  selected: null,
  drawing: false,
  profileLine: [],
  densities: [2670, 2300],
  theme: "system",
  set: (patch) => set(patch),
}));
