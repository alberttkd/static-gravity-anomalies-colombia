import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../../src/App";
import { SourceContext } from "../../src/api/hooks";
import type { DataSource } from "../../src/api/source";
import type { StationCollection } from "../../src/api/types";
import { ProfileChart } from "../../src/components/Charts";
import { Legend } from "../../src/components/Legend";
import { DEFAULT_REDUCTION, useUi } from "../../src/state/store";

const stations: StationCollection = {
  type: "FeatureCollection",
  properties: { label: "SYNTHETIC" },
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-75, 9] },
      properties: {
        station_uid: "SYN:A", qc_flags: [], lon: -75, lat: 9, height_m: 100, g_obs_mgal: 978100, gamma0_mgal: 978150,
        honkasalo_mgal: 0.034, height_corr_mgal: 30.87, atm_mgal: 0.86, faa_mgal: -18.2, bc_slab_mgal: 11.2, sba_mgal: -29.4,
        bb_mgal: 0.14, tc_rho_mgal: 0.3, cba_mgal: -29.25, sigma_faa_mgal: 0.33, sigma_sba_mgal: 0.22, sigma_cba_mgal: 0.22,
      },
    },
    { type: "Feature", geometry: { type: "Point", coordinates: [-75.1, 9.1] }, properties: { station_uid: "SYN:B", qc_flags: ["TC_SUSPECT"], cba_mgal: null, faa_mgal: 3 } },
  ],
};

const cv = {
  method: "rk_matern",
  outer: { rmse: 0.67, mae: 0.5, me: 0, r2: 0.99, n: 2 },
  fold_rmse_mean: 0.66,
  fold_rmse_sd: 0.1,
  folds: [{ fold: 0, chosen: "rk_d2_nu1.5", rmse: 0.6, n_test: 2, calibration_c: 0.73 }],
  calibrated: { sd_z: 0.9, coverage95: 0.96, n: 2 },
  points: { observed: [1, 2], predicted: [1.1, 1.9], z: [0.2, -0.3] },
};

function fakeSource(mode: "live" | "static" = "static"): DataSource {
  return {
    mode,
    datasets: async () => [{ id: "synthetic", kind: "synthetic", label: "SYNTHETIC", n_stations: 2, extent: [-76, 8, -74, 10] }],
    reduce: async (_d, c) => ({ run_id: c.density_kg_m3 === 2300 ? "R-2300" : "R", config_hash: "h", dataset: "synthetic", label: "SYNTHETIC", summary: {} }),
    stations: async () => stations,
    qc: async () => ({ n_stations: 2, flag_counts: { TC_SUSPECT: 1, ERROR_RANGE: 0 }, harmonization: { n_records_in: 3, n_positions: 2, n_merged_groups: 1, merged_groups: [{ station_uid: "m", members: ["a", "b"], g_spread_mgal: 0.5 }], repeat_precision_sigma_g_mgal: 0.35 }, bb_comparison: { per_source: { G10: { ratio_median: -0.999, n: 5 } } } }),
    density: async () => ({
      densities_kg_m3: [2670, 2300],
      delta: new Map([["SYN:A", -1.2]]),
      stats: { mean: -1.2, min: -1.2, max: -1.2, n: 1 },
      diagnostics: { nettleton: { estimate_kg_m3: 2530, ci95_kg_m3: [2050, 3000] }, parasnis: { estimate_kg_m3: 2500, ci95_kg_m3: [2000, 2970] }, nettleton_curve: { rho_kg_m3: [1800, 3000], corr: [0.1, -0.1] }, h5: { supported: true, statement: "" } },
    }),
    submitGrid: async () => ({ job_id: "J", status: "done", progress: 1, grid_id: "G" }),
    job: async () => ({ job_id: "J", status: "done", progress: 1, grid_id: "G" }),
    grid: async () => ({ grid_id: "G", target: "CBA", method: "rk_matern", cell_size_m: 500, units: "mGal", crs: "EPSG:9377", layers: ["value", "sigma_cal"] }),
    layerImage: async (_g, layer) => ({ url: `/demo/${layer}.png`, bounds: [-76, 8, -74, 10], vmin: -5, vmax: 5, cmap: layer === "sigma_cal" ? "viridis" : "RdBu_r", units: "mGal" }),
    contours: async () => ({ type: "FeatureCollection", features: [{ type: "Feature", properties: { level: 5 }, geometry: { type: "LineString", coordinates: Array.from({ length: 20 }, (_, i) => [-75 + i * 0.01, 9]) } }] }),
    validation: async () => ({
      cv: { rk_matern: cv, idw: { ...cv, method: "idw", outer: { ...cv.outer, rmse: 2.5 }, calibrated: undefined } },
      selection: { selected: "rk_matern", rmse: { idw: 2.5, rk_matern: 0.67 }, ratio_to_idw: 0.27, rationale: [] },
      variogram: { model: { nu: 1.5, nugget: 0.1, psill: 100, length_m: 40000 }, experimental: { lag_m: [1000, 2000], gamma_mgal2: [1, 2], n_pairs: [10, 20] }, directional: [{ lag_m: [1000], gamma_mgal2: [1], n_pairs: [5], direction_deg: 0 }], fitted_curve: { lag_m: [0, 1000], gamma_mgal2: [0, 1] } },
    }),
    profile: async () => ({ distance_km: [0, 1], value: [1, null], sigma: [0.5, null], supported: [true, false], length_km: 1, stations: [{ station_uid: "SYN:A", distance_km: 0.2, offset_m: 100, value: 1, sigma: 0.2, height_m: 100 }], units: "mGal" }),
    manifest: async () => ({ run_id: "R", label: "SYNTHETIC", config_hash: "abcdef0123456789", inputs: { "synthetic_survey.csv": "0123456789abcdef" }, versions: { gravanom: "0.1.0" }, seeds: { cv: 20261022 }, git_commit: "deadbeefcafe", config: { reduction: {} } }),
    downloadUrl: (kind, id, format) => (mode === "live" ? `/api/${kind}/${id}.${format}` : null),
  };
}

function renderApp(src: DataSource, ui: ReactNode = <App />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SourceContext.Provider value={src}>{ui}</SourceContext.Provider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUi.setState({ dataset: "synthetic", quantity: "cba_mgal", reduction: DEFAULT_REDUCTION, runId: null, gridId: null, jobId: null, tab: "station", selected: null, drawing: false, profileLine: [], densities: [2670, 2300], theme: "system", gridLayer: "value" });
});

describe("App (static demo)", () => {
  it("shows the SYNTHETIC badge, mGal legend, CRS attribution and the precomputed grid", async () => {
    renderApp(fakeSource("static"));
    expect(await screen.findByTestId("dataset-badge")).toHaveTextContent("SYNTHETIC DATA");
    expect(screen.getByText(/EPSG:9377/)).toBeInTheDocument();
    expect(screen.getAllByText("(mGal)").length).toBeGreaterThan(0);
    await waitFor(() => expect(useUi.getState().gridId).toBe("G"));
    expect(await screen.findByText(/Grid layer/)).toBeInTheDocument();
  });

  it("selects a station from the map and shows the reduction breakdown", async () => {
    renderApp(fakeSource());
    await waitFor(() => expect(useUi.getState().runId).toBe("R"));
    act(() => useUi.getState().set({ selected: "SYN:A" }));
    expect(await screen.findByText("Reduction breakdown (mGal)")).toBeInTheDocument();
    expect(screen.getAllByText("Complete Bouguer anomaly").length).toBeGreaterThan(1);
    expect(screen.getAllByText("−29.25").length).toBeGreaterThan(0);
  });

  it("switches quantities, tabs and theme", async () => {
    renderApp(fakeSource());
    fireEvent.click(await screen.findByRole("radio", { name: "Height" }));
    expect(useUi.getState().quantity).toBe("height_m");
    fireEvent.click(screen.getByRole("radio", { name: "QC flag" }));
    expect(await screen.findByText("Error (excluded)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Theme/ }));
    expect(useUi.getState().theme).toBe("light");
    fireEvent.click(screen.getByRole("tab", { name: "QC" }));
    expect(await screen.findByText("TC_SUSPECT")).toBeInTheDocument();
    expect(await screen.findByText("Download QC report (JSON)")).toBeInTheDocument();
    expect(screen.getByText("σ_g from repeat pairs")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Provenance" }));
    expect(await screen.findByTestId("provenance")).toHaveTextContent("20261022");
  });

  it("validates the density input and runs a new reduction", async () => {
    renderApp(fakeSource("live"));
    const input = await screen.findByLabelText("Bouguer density (kg/m³)");
    fireEvent.change(input, { target: { value: "900" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("between 1000 and 3500");
    fireEvent.change(input, { target: { value: "2300" } });
    fireEvent.click(screen.getByRole("button", { name: "Run reduction" }));
    await waitFor(() => expect(useUi.getState().runId).toBe("R-2300"));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(useUi.getState().reduction.density_kg_m3).toBe(2670);
  });

  it("runs gridding and shows validation charts and tables", async () => {
    renderApp(fakeSource("live"));
    await waitFor(() => expect(useUi.getState().runId).toBe("R"));
    fireEvent.click(screen.getByRole("button", { name: "Run gridding" }));
    await waitFor(() => expect(useUi.getState().gridId).toBe("G"));
    fireEvent.click(screen.getByRole("tab", { name: "Validation" }));
    expect(await screen.findByText(/Selected \/ IDW RMSE/)).toBeInTheDocument();
    expect(screen.getByText("rk_d2_nu1.5")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Pred. vs obs." }));
    fireEvent.click(screen.getByRole("radio", { name: "z histogram" }));
    fireEvent.click(screen.getByText("IDW p=2, k=12"));
    fireEvent.click(screen.getByRole("radio", { name: "σ cal." }));
    expect(useUi.getState().gridLayer).toBe("sigma_cal");
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(within(screen.getByRole("menu")).getByText(/COG GeoTIFF/)).toBeInTheDocument();
  });

  it("computes a profile from typed coordinates and handles the density tab", async () => {
    renderApp(fakeSource("live"));
    await waitFor(() => expect(useUi.getState().runId).toBe("R"));
    act(() => useUi.getState().set({ gridId: "G", tab: "profile" }));
    const input = await screen.findByLabelText(/Or type vertices/);
    fireEvent.change(input, { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(await screen.findByText(/at least two lon,lat pairs/)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "-75.3,9; -74.7,9" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(await screen.findByTestId("profile-chart")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Draw on map" }));
    expect(useUi.getState().drawing).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "Density" }));
    expect(await screen.findByText(/H5 supported/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(useUi.getState().quantity).toBe("delta_cba_mgal");
  });
});

describe("components", () => {
  it("renders a legend with symmetric ticks", () => {
    render(<Legend title="CBA" units="mGal" limits={[-10, 10]} cmap="RdBu_r" />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("−10")).toBeInTheDocument();
  });

  it("renders a profile chart summary", () => {
    render(<ProfileChart p={{ distance_km: [0, 1], value: [1, 2], sigma: [0.1, 0.2], supported: [true, true], length_km: 12.3, stations: [], units: "mGal" }} />);
    expect(screen.getByText(/12.3 km/)).toBeInTheDocument();
  });
});
