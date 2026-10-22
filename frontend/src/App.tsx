import { useEffect, useMemo, useState } from "react";
import { useContours, useDatasets, useDensity, useLayerImage, useReferenceRun, useRun, useSource, useStations } from "./api/hooks";
import { Header } from "./components/Header";
import { Inspector } from "./components/Inspector";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import { GridDisplayPanel, GriddingPanel, LayerPanel, ReductionPanel } from "./components/Sidebar";
import { ErrorNote } from "./components/ui";
import { en } from "./i18n/en";
import { cmapFor, limitsFor, type CmapName } from "./lib/colormaps";
import { deriveStations, values } from "./lib/derive";
import { useUi } from "./state/store";

function useSystemDark(): boolean {
  const [dark, setDark] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return !!dark;
}

export default function App() {
  const ui = useUi();
  const src = useSource();
  const systemDark = useSystemDark();
  const datasets = useDatasets();
  const run = useRun(ui.dataset, ui.reduction);
  const ref = useReferenceRun(ui.dataset);
  const stations = useStations(run.data?.run_id);
  const refStations = useStations(ref.data?.run_id);
  const wantDensity = ui.quantity === "delta_cba_mgal" || ui.tab === "density";
  const density = useDensity(ui.dataset, ui.densities, wantDensity);
  const { set } = ui;

  useEffect(() => {
    document.documentElement.dataset.theme = ui.theme === "system" ? "" : ui.theme;
    if (ui.theme === "system") delete document.documentElement.dataset.theme;
  }, [ui.theme]);

  useEffect(() => {
    if (run.data?.run_id && run.data.run_id !== ui.runId) set({ runId: run.data.run_id });
  }, [run.data, ui.runId, set]);

  // Static demo: the precomputed grid is available immediately.
  useEffect(() => {
    if (src.mode === "static" && !ui.gridId) void src.submitGrid("", {}).then((j) => j.grid_id && set({ gridId: j.grid_id }));
  }, [src, ui.gridId, set]);

  const derived = useMemo(() => deriveStations(stations.data, refStations.data, density.data?.delta), [stations.data, refStations.data, density.data]);
  // Read-only hook for end-to-end tests (AT-02/AT-05 compare displayed values with the API).
  useEffect(() => {
    (window as unknown as { __gravanom?: unknown }).__gravanom = { stations: derived, runId: run.data?.run_id, gridId: ui.gridId };
  }, [derived, run.data, ui.gridId]);

  const prop = ui.quantity;
  const categorical = prop === "qc";
  const cmap: CmapName = cmapFor(prop);
  const limits = useMemo(() => limitsFor(prop, values(derived, prop)), [derived, prop]);

  const img = useLayerImage(ui.gridId, ui.gridLayer);
  const hatch = useLayerImage(ui.gridId, "lowconf_hatch", ui.showHatch);
  const contourLayer = ui.gridLayer === "residual" ? "residual" : ui.gridLayer === "trend" ? "trend" : "value";
  const contours = useContours(ui.gridId, contourLayer, ui.showContours && ui.gridLayer !== "sigma_cal");
  const extent = datasets.data?.find((d) => d.id === ui.dataset)?.extent;
  const units = prop === "height_m" ? "m" : categorical ? "" : "mGal";
  const themeKey = `${ui.theme}-${systemDark}`;

  return (
    <div className="grid h-full grid-rows-[52px_1fr]">
      <a href="#inspector" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-surface focus:p-2">
        Skip to results
      </a>
      <Header />
      <main className="grid min-h-0 grid-cols-1 overflow-y-auto lg:grid-cols-[300px_minmax(0,1fr)_400px] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden">
        <aside aria-label="Controls" className="flex flex-col gap-6 border-b border-line bg-surface p-4 lg:overflow-y-auto lg:border-r lg:border-b-0">
          <LayerPanel hasDensity={!!density.data || wantDensity} />
          <GridDisplayPanel />
          <ReductionPanel />
          <GriddingPanel />
          {run.error ? <ErrorNote error={run.error} retry={() => void run.refetch()} /> : null}
          {stations.error ? <ErrorNote error={stations.error} retry={() => void stations.refetch()} /> : null}
        </aside>
        <section aria-label="Map" className="relative h-[60vh] min-h-[360px] bg-surface-2 lg:h-auto">
          <MapView
            stations={derived}
            colorProperty={prop}
            limits={limits}
            cmap={cmap}
            categorical={categorical}
            selected={ui.selected}
            onSelect={(uid) => set({ selected: uid, ...(uid ? { tab: "station" } : {}) })}
            extent={extent}
            gridImage={img.data}
            hatchImage={ui.showHatch ? hatch.data : undefined}
            showGrid={ui.showGrid}
            opacity={ui.opacity}
            contours={ui.showContours ? contours.data : undefined}
            drawing={ui.drawing}
            profileLine={ui.profileLine}
            onAddVertex={(p) => set({ profileLine: [...ui.profileLine, p] })}
            themeKey={themeKey}
          />
          <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-2">
            {img.data && ui.showGrid ? (
              <div className="pointer-events-auto">
                <Legend
                  title={`Grid: ${en.gridLayers[ui.gridLayer] ?? ui.gridLayer}`}
                  units={img.data.units || "mGal"}
                  limits={[img.data.vmin ?? -1, img.data.vmax ?? 1]}
                  cmap={(img.data.cmap === "viridis" ? "viridis" : "RdBu_r") as CmapName}
                />
              </div>
            ) : null}
            <div className="pointer-events-auto">
              <Legend title={en.longNames[prop] ?? en.quantities[prop] ?? prop} units={units} limits={limits} cmap={cmap} categorical={categorical} />
            </div>
          </div>
          <p className="absolute top-3 left-3 rounded-[6px] bg-surface/85 px-2 py-1 text-[11px] text-fg-3">{en.attribution}</p>
          {stations.isLoading ? (
            <div className="absolute inset-x-0 top-0 h-0.5 overflow-hidden" aria-label="Loading stations" role="progressbar">
              <div className="skeleton h-full w-full" />
            </div>
          ) : null}
        </section>
        <aside id="inspector" aria-label="Inspector" className="flex min-h-[480px] flex-col border-t border-line bg-surface lg:min-h-0 lg:border-t-0 lg:border-l">
          <Inspector stations={derived} />
        </aside>
      </main>
    </div>
  );
}
