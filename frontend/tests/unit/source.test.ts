import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveSource, StaticSource, createSource } from "../../src/api/source";
import { ApiError } from "../../src/api/types";

function mockFetch(routes: Record<string, unknown>, status = 200) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    const key = Object.keys(routes).find((k) => url.includes(k));
    const body = key ? routes[key] : { code: "NOT_FOUND", detail: "missing" };
    return new Response(JSON.stringify(body), { status: key ? status : 404, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

const index = {
  label: "SYNTHETIC",
  run_id: "R1",
  dataset: { id: "synthetic", kind: "synthetic", n_stations: 2 },
  grids: [{ grid_id: "G1", target: "CBA", method: "rk_matern", cell_size_m: 500, crs: "EPSG:9377", images: { value: { file: "g_value.png", bounds: [-76, 8, -74, 10], vmin: -5, vmax: 5 }, lowconf_hatch: { file: "h.png", bounds: [-76, 8, -74, 10] } }, contours: "c.geojson", contours_residual: "cr.geojson" }],
  cv: ["idw", "rk_matern"],
};
const stations = {
  type: "FeatureCollection",
  properties: { label: "SYNTHETIC" },
  features: [
    { type: "Feature", geometry: { type: "Point", coordinates: [-75, 9] }, properties: { station_uid: "A", qc_flags: [], cba_mgal: -10, cba_2300_mgal: -9 } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-75, 9.1] }, properties: { station_uid: "B", qc_flags: [], cba_mgal: -4, cba_2300_mgal: -3.5 } },
  ],
};

describe("StaticSource", () => {
  it("serves precomputed runs, grids, density and validation", async () => {
    mockFetch({
      "index.json": index,
      "stations.geojson": stations,
      "density_report.json": { nettleton: {}, parasnis: {}, nettleton_curve: { rho_kg_m3: [], corr: [] }, h5: { supported: true } },
      "cv/idw.json": { method: "idw" },
      "cv/rk_matern.json": { method: "rk_matern" },
      "selection.json": { selected: "rk_matern" },
      "variogram.json": { note: "x" },
      "c.geojson": { type: "FeatureCollection", features: [] },
      "qc_report.json": { n_stations: 2 },
      "manifest.json": { run_id: "R1" },
    });
    const s = new StaticSource("/demo");
    expect((await s.datasets())[0]?.label).toBe("SYNTHETIC");
    const r = await s.reduce("synthetic", { density_kg_m3: 2300 });
    expect(r.run_id).toBe("R1-2300");
    const fc = await s.stations(r.run_id);
    expect(fc.features[0]?.properties.cba_mgal).toBe(-9);
    await expect(s.reduce("synthetic", { legacy_mode: true })).rejects.toBeInstanceOf(ApiError);
    expect((await s.reduce("synthetic", { density_kg_m3: 2670, honkasalo: true, legacy_mode: false })).run_id).toBe("R1");
    const d = await s.density("synthetic", [2670, 2300]);
    expect(d.delta.get("A")).toBe(-1);
    expect(d.stats.n).toBe(2);
    await expect(s.density("synthetic", [2500, 2300])).rejects.toBeInstanceOf(ApiError);
    const j = await s.submitGrid();
    expect(j.grid_id).toBe("G1");
    expect((await s.job()).status).toBe("done");
    const g = await s.grid("G1");
    expect(g.layers).toEqual(["value"]);
    expect((await s.layerImage("G1", "value")).url).toBe("/demo/g_value.png");
    await expect(s.layerImage("G1", "trend")).rejects.toBeInstanceOf(ApiError);
    await expect(s.grid("nope")).rejects.toBeInstanceOf(ApiError);
    expect((await s.contours("G1", "value")).type).toBe("FeatureCollection");
    const v = await s.validation();
    expect(Object.keys(v.cv)).toEqual(["idw", "rk_matern"]);
    expect(v.selection?.selected).toBe("rk_matern");
    expect(() => s.profile()).toThrow(ApiError);
    expect((await s.qc()).n_stations).toBe(2);
    expect((await s.manifest()).run_id).toBe("R1");
    expect(s.downloadUrl()).toBeNull();
  });
});

describe("LiveSource", () => {
  it("calls the API and maps problem+json errors", async () => {
    const f = mockFetch({
      "/datasets": [{ id: "synthetic" }],
      "/reductions/R/stations": stations,
      "/image-meta": { bounds: [0, 0, 1, 1], vmin: -1, vmax: 1 },
      "/sensitivity/density": { densities_kg_m3: [2670, 2300], stats: {}, stations: { ...stations, features: stations.features.map((x) => ({ ...x, properties: { ...x.properties, delta_cba_mgal: -1 } })) }, diagnostics: {} },
    });
    const s = new LiveSource("/api/v1");
    expect((await s.datasets())[0]?.id).toBe("synthetic");
    expect((await s.stations("R")).features).toHaveLength(2);
    expect((await s.layerImage("G", "value")).url).toBe("/api/v1/grids/G/image?layer=value");
    expect((await s.density("synthetic", [2670, 2300])).delta.get("B")).toBe(-1);
    expect(s.downloadUrl("grid", "G", "cog", "sigma_cal")).toContain("layer=sigma_cal");
    expect(s.downloadUrl("stations", "R", "csv")).toContain("/reductions/R/export?format=csv");
    const err = await s.grid("missing").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("NOT_FOUND");
    expect(f).toHaveBeenCalled();
  });

  it("issues POSTs with JSON bodies", async () => {
    const f = mockFetch({ "/reductions": { run_id: "R" }, "/gridding-jobs": { job_id: "J", status: "queued" }, "/profile": { distance_km: [] } });
    const s = new LiveSource();
    await s.reduce("synthetic", { density_kg_m3: 2300 });
    await s.submitGrid("R", { method: "idw" });
    await s.profile("G", [[0, 0], [1, 1]], 2000);
    const body = JSON.parse(String((f.mock.calls[0]?.[1] as RequestInit).body));
    expect(body).toEqual({ dataset: "synthetic", config: { density_kg_m3: 2300 } });
  });

  it("selects the implementation from the build mode", () => {
    expect(createSource().mode).toBe("live");
  });
});
