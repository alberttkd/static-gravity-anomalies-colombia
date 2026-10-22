/** Front-end data shapes. Request bodies mirror the OpenAPI schema (src/api/schema.d.ts). */
import type { components } from "./schema";

export type ReductionConfig = components["schemas"]["ReductionConfig"];
export type GriddingConfig = components["schemas"]["GriddingConfig"];

export type Props = Record<string, unknown> & { station_uid: string; qc_flags: string[] };

export interface StationFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: Props;
}

export interface StationCollection {
  type: "FeatureCollection";
  features: StationFeature[];
  properties: { label: string; run_id?: string; config_hash?: string };
}

export interface DatasetInfo {
  id: string;
  kind: "synthetic" | "private";
  label: string;
  n_stations: number;
  extent?: [number, number, number, number];
}

export interface RunInfo {
  run_id: string;
  config_hash: string;
  dataset: string;
  label: string;
  summary: Record<string, unknown>;
}

export interface GridMeta {
  grid_id: string;
  run_id?: string;
  target: string;
  method: string;
  calibration_c?: number | null;
  cell_size_m: number;
  units: string;
  crs: string;
  supported_share?: number;
  cv?: { rmse?: number; sd_z?: number; coverage95?: number };
  layers: string[];
  params?: Record<string, unknown>;
}

export interface LayerImage {
  url: string;
  bounds: [number, number, number, number];
  vmin?: number;
  vmax?: number;
  cmap?: string;
  units?: string;
}

export interface CvReport {
  method: string;
  outer: { rmse: number; mae: number; me: number; r2: number; n: number };
  fold_rmse_mean: number;
  fold_rmse_sd: number;
  folds: { fold: number; chosen: string; rmse: number; n_test: number; calibration_c?: number | null; calibration?: { sd_z: number; coverage95: number } }[];
  calibrated?: { sd_z: number; coverage95: number; n: number };
  raw?: { sd_z: number; coverage95: number; n: number };
  points: { observed: number[]; predicted: number[]; z?: number[] };
}

export interface Variogram {
  model?: { nu: number; nugget: number; psill: number; length_m: number };
  params?: Record<string, unknown>;
  experimental?: { lag_m: number[]; gamma_mgal2: number[]; n_pairs: number[] };
  directional?: { lag_m: number[]; gamma_mgal2: number[]; n_pairs: number[]; direction_deg: number | null }[];
  fitted_curve?: { lag_m: number[]; gamma_mgal2: number[] };
  calibration_c?: number | null;
  note?: string;
}

export interface Validation {
  method?: string;
  selection?: { selected: string; rmse: Record<string, number>; ratio_to_idw?: number | null; rationale: string[] };
  cv: Record<string, CvReport>;
  variogram?: Variogram;
}

export interface ProfileData {
  distance_km: number[];
  value: (number | null)[];
  sigma: (number | null)[];
  supported: boolean[];
  length_km: number;
  stations: { station_uid: string; distance_km: number; offset_m: number; value: number; sigma: number | null; height_m: number }[];
  units: string;
}

export interface DensityResult {
  densities_kg_m3: [number, number];
  stats: { mean: number; min: number; max: number; n: number };
  delta: Map<string, number>;
  diagnostics: Record<string, unknown> & {
    nettleton: { estimate_kg_m3: number; ci95_kg_m3: [number, number]; at_grid_boundary?: boolean };
    parasnis: { estimate_kg_m3: number; ci95_kg_m3: [number, number] };
    nettleton_curve: { rho_kg_m3: number[]; corr: number[] };
    h5: { supported: boolean; statement: string };
  };
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  grid_id?: string;
  error?: { code: string; detail: string };
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
