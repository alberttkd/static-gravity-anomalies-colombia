/**
 * Data access. `LiveSource` talks to the FastAPI backend (/api/v1); `StaticSource` reads the
 * precomputed synthetic demo exported by `gravanom export-static-demo` (no backend, no real data).
 */
import {
  ApiError,
  type CvReport,
  type DatasetInfo,
  type DensityResult,
  type GridMeta,
  type GriddingConfig,
  type JobStatus,
  type LayerImage,
  type ProfileData,
  type ReductionConfig,
  type RunInfo,
  type StationCollection,
  type Validation,
  type Variogram,
} from "./types";

export interface DataSource {
  readonly mode: "live" | "static";
  datasets(): Promise<DatasetInfo[]>;
  reduce(dataset: string, config: Partial<ReductionConfig>): Promise<RunInfo>;
  stations(runId: string): Promise<StationCollection>;
  qc(dataset: string): Promise<Record<string, unknown>>;
  density(dataset: string, densities: [number, number]): Promise<DensityResult>;
  submitGrid(runId: string, config: Partial<GriddingConfig>): Promise<JobStatus>;
  job(jobId: string): Promise<JobStatus>;
  grid(gridId: string): Promise<GridMeta>;
  layerImage(gridId: string, layer: string): Promise<LayerImage>;
  contours(gridId: string, layer: string): Promise<GeoJSON.FeatureCollection>;
  validation(gridId: string): Promise<Validation>;
  profile(gridId: string, coordinates: [number, number][], bufferM: number): Promise<ProfileData>;
  manifest(runId: string): Promise<Record<string, unknown>>;
  downloadUrl(kind: "grid" | "stations", id: string, format: string, layer?: string): string | null;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = "HTTP_ERROR";
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { code?: string; detail?: string };
      code = body.code ?? code;
      detail = body.detail ?? detail;
    } catch {
      /* not a problem+json body */
    }
    throw new ApiError(res.status, code, detail);
  }
  return (await res.json()) as T;
}

function deltaMap(fc: StationCollection, key: string): Map<string, number> {
  const m = new Map<string, number>();
  for (const f of fc.features) {
    const v = f.properties[key];
    if (typeof v === "number") m.set(f.properties.station_uid, v);
  }
  return m;
}

export class LiveSource implements DataSource {
  readonly mode = "live" as const;
  constructor(private base = "/api/v1") {}

  private get<T>(path: string): Promise<T> {
    return fetch(this.base + path).then((r) => json<T>(r));
  }

  private post<T>(path: string, body: unknown): Promise<T> {
    return fetch(this.base + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<T>(r));
  }

  datasets() {
    return this.get<DatasetInfo[]>("/datasets");
  }
  reduce(dataset: string, config: Partial<ReductionConfig>) {
    return this.post<RunInfo>("/reductions", { dataset, config });
  }
  stations(runId: string) {
    return this.get<StationCollection>(`/reductions/${encodeURIComponent(runId)}/stations`);
  }
  qc(dataset: string) {
    return this.get<Record<string, unknown>>(`/datasets/${dataset}/qc`);
  }
  async density(dataset: string, densities: [number, number]): Promise<DensityResult> {
    const r = await this.post<Omit<DensityResult, "delta"> & { stations: StationCollection }>("/sensitivity/density", {
      dataset,
      densities,
    });
    return { ...r, delta: deltaMap(r.stations, "delta_cba_mgal") };
  }
  submitGrid(runId: string, config: Partial<GriddingConfig>) {
    return this.post<JobStatus>("/gridding-jobs", { run_id: runId, config });
  }
  job(jobId: string) {
    return this.get<JobStatus>(`/gridding-jobs/${jobId}`);
  }
  grid(gridId: string) {
    return this.get<GridMeta>(`/grids/${gridId}`);
  }
  async layerImage(gridId: string, layer: string): Promise<LayerImage> {
    const meta = await this.get<Omit<LayerImage, "url">>(`/grids/${gridId}/image-meta?layer=${layer}`);
    return { ...meta, url: `${this.base}/grids/${gridId}/image?layer=${layer}` };
  }
  contours(gridId: string, layer: string) {
    const interval = layer === "residual" ? 1 : 5;
    return this.get<GeoJSON.FeatureCollection>(`/grids/${gridId}/contours?interval=${interval}&layer=${layer}`);
  }
  validation(gridId: string) {
    return this.get<Validation>(`/grids/${gridId}/validation`);
  }
  profile(gridId: string, coordinates: [number, number][], bufferM: number) {
    return this.post<ProfileData>(`/grids/${gridId}/profile`, { coordinates, buffer_m: bufferM });
  }
  manifest(runId: string) {
    return this.get<Record<string, unknown>>(`/runs/${encodeURIComponent(runId)}/manifest`);
  }
  downloadUrl(kind: "grid" | "stations", id: string, format: string, layer = "value") {
    return kind === "grid"
      ? `${this.base}/grids/${id}/download?format=${format}&layer=${layer}`
      : `${this.base}/reductions/${encodeURIComponent(id)}/export?format=${format}`;
  }
}

interface DemoIndex {
  label: string;
  run_id: string;
  dataset: DatasetInfo;
  grids: (GridMeta & {
    images: Record<string, { file: string; bounds: [number, number, number, number]; vmin?: number; vmax?: number; cmap?: string; units?: string }>;
    contours: string;
    contours_residual: string;
  })[];
  cv: string[];
}

const STATIC_DEFAULTS: Partial<ReductionConfig> = {
  normal_gravity: "GRS80_closed_form",
  height_correction: "hinze2005_second_order",
  honkasalo: true,
  atmospheric: true,
  curvature: "lafehr1991_closed_form",
  terrain_source: "supplied",
  terrain_reference_density_kg_m3: 2670,
  legacy_mode: false,
};

/** Static demo: two precomputed runs (2670 and 2300 kg/m3) and one precomputed grid. */
export class StaticSource implements DataSource {
  readonly mode = "static" as const;
  private index: Promise<DemoIndex> | null = null;
  private fc: Promise<StationCollection> | null = null;

  constructor(private base = "./demo") {}

  private file<T>(name: string): Promise<T> {
    return fetch(`${this.base}/${name}`).then((r) => json<T>(r));
  }
  private idx(): Promise<DemoIndex> {
    this.index ??= this.file<DemoIndex>("index.json");
    return this.index;
  }
  private all(): Promise<StationCollection> {
    this.fc ??= this.file<StationCollection>("stations.geojson");
    return this.fc;
  }
  private static unavailable(): never {
    throw new ApiError(501, "STATIC_MODE", "This action needs the API (full mode).");
  }

  async datasets() {
    const i = await this.idx();
    return [{ ...i.dataset, label: i.label }];
  }
  async reduce(dataset: string, config: Partial<ReductionConfig>): Promise<RunInfo> {
    const i = await this.idx();
    // Only the two precomputed runs exist: every option except density must keep its default.
    const keys = (Object.keys(config) as (keyof ReductionConfig)[]).filter(
      (k) => k !== "density_kg_m3" && config[k] !== undefined && config[k] !== STATIC_DEFAULTS[k],
    );
    const rho = config.density_kg_m3 ?? 2670;
    if (keys.length || (rho !== 2670 && rho !== 2300)) StaticSource.unavailable();
    return { run_id: rho === 2300 ? `${i.run_id}-2300` : i.run_id, config_hash: "", dataset, label: i.label, summary: {} };
  }
  async stations(runId: string): Promise<StationCollection> {
    const fc = await this.all();
    if (!runId.endsWith("-2300")) return fc;
    return {
      ...fc,
      features: fc.features.map((f) => ({ ...f, properties: { ...f.properties, cba_mgal: f.properties.cba_2300_mgal } })),
    };
  }
  qc() {
    return this.file<Record<string, unknown>>("qc_report.json");
  }
  async density(_dataset: string, densities: [number, number]): Promise<DensityResult> {
    const [a, b] = densities;
    if (!((a === 2670 && b === 2300) || (a === 2300 && b === 2670))) StaticSource.unavailable();
    const fc = await this.all();
    const delta = new Map<string, number>();
    for (const f of fc.features) {
      const x = f.properties.cba_mgal;
      const y = f.properties.cba_2300_mgal;
      if (typeof x === "number" && typeof y === "number") delta.set(f.properties.station_uid, a === 2670 ? x - y : y - x);
    }
    const v = [...delta.values()];
    const diagnostics = await this.file<DensityResult["diagnostics"]>("density_report.json");
    return {
      densities_kg_m3: densities,
      delta,
      stats: { mean: v.reduce((s, x) => s + x, 0) / v.length, min: Math.min(...v), max: Math.max(...v), n: v.length },
      diagnostics,
    };
  }
  async submitGrid(): Promise<JobStatus> {
    const i = await this.idx();
    return { job_id: "static", status: "done", progress: 1, grid_id: i.grids[0]?.grid_id };
  }
  async job(): Promise<JobStatus> {
    return this.submitGrid();
  }
  private async gridEntry(gridId: string) {
    const g = (await this.idx()).grids.find((x) => x.grid_id === gridId);
    if (!g) throw new ApiError(404, "NOT_FOUND", `grid ${gridId} not found`);
    return g;
  }
  async grid(gridId: string): Promise<GridMeta> {
    const g = await this.gridEntry(gridId);
    return { ...g, units: "mGal", layers: Object.keys(g.images).filter((l) => l !== "lowconf_hatch") };
  }
  async layerImage(gridId: string, layer: string): Promise<LayerImage> {
    const img = (await this.gridEntry(gridId)).images[layer];
    if (!img) throw new ApiError(404, "NOT_FOUND", `layer ${layer} not exported`);
    return { ...img, url: `${this.base}/${img.file}` };
  }
  async contours(gridId: string, layer: string) {
    const g = await this.gridEntry(gridId);
    return this.file<GeoJSON.FeatureCollection>(layer === "residual" ? g.contours_residual : g.contours);
  }
  async validation(): Promise<Validation> {
    const i = await this.idx();
    const cvs = await Promise.all(i.cv.map((m) => this.file<CvReport>(`cv/${m}.json`)));
    const [selection, variogram] = await Promise.all([
      this.file<Validation["selection"]>("selection.json").catch(() => undefined),
      this.file<Variogram>("variogram.json"),
    ]);
    return { cv: Object.fromEntries(i.cv.map((m, k) => [m, cvs[k] as CvReport])), selection, variogram };
  }
  profile(): Promise<ProfileData> {
    StaticSource.unavailable();
  }
  manifest() {
    return this.file<Record<string, unknown>>("manifest.json");
  }
  downloadUrl() {
    return null;
  }
}

export function createSource(): DataSource {
  return import.meta.env.VITE_STATIC_MODE === "1" ? new StaticSource() : new LiveSource();
}
