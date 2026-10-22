import { useMemo, useState } from "react";
import { useDensity, useProfile, useSource, useValidation } from "../api/hooks";
import type { CvReport, ProfileData } from "../api/types";
import { en } from "../i18n/en";
import { fmt } from "../lib/colormaps";
import { histogram, parseCoordinates } from "../lib/derive";
import { useUi } from "../state/store";
import { Plot, themeColor } from "./Plot";
import { Button, Empty, ErrorNote, Field, Segmented, SkeletonLines, Stat, inputClass } from "./ui";

const METHOD_NAMES: Record<string, string> = {
  idw: "IDW p=2, k=12",
  spline: "Trend(1) + spline",
  rk_matern: "RK Matérn",
  eqs: "Equivalent sources",
};

export function ValidationPanel() {
  const { gridId } = useUi();
  const v = useValidation(gridId);
  const [method, setMethod] = useState<string | null>(null);
  const [plot, setPlot] = useState<"variogram" | "scatter" | "z">("variogram");
  if (!gridId) return <Empty>{en.emptyGrid}</Empty>;
  if (v.isLoading) return <SkeletonLines lines={8} />;
  if (v.error) return <ErrorNote error={v.error} retry={() => void v.refetch()} />;
  const data = v.data;
  if (!data) return null;
  const selected = data.selection?.selected ?? data.method ?? Object.keys(data.cv)[0] ?? "";
  const m = method ?? selected;
  const rep = data.cv[m] as CvReport | undefined;
  const accent = themeColor("--accent", "#b45309");
  const fg = themeColor("--text", "#18181b");
  const fg3 = themeColor("--text-3", "#71717a");

  return (
    <div className="flex flex-col gap-4">
      {rep ? (
        <div className="grid grid-cols-3 border-y border-line">
          <Stat k="Block-CV RMSE" v={fmt(rep.outer.rmse, 3)} s="mGal" />
          <Stat k="sd(z)" v={rep.calibrated ? fmt(rep.calibrated.sd_z, 3) : "n/a"} s="target 0.85-1.15" />
          <Stat k="95 % coverage" v={rep.calibrated ? fmt(rep.calibrated.coverage95, 3) : "n/a"} s="target 0.92-0.98" />
        </div>
      ) : null}
      <div>
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Method comparison (nested block CV)</h3>
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-fg-3">
              <th className="py-1 text-left font-normal">Method</th>
              <th className="py-1 text-right font-normal">RMSE (mGal)</th>
              <th className="py-1 text-right font-normal">Fold sd</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.cv).map(([k, r]) => (
              <tr key={k} aria-selected={k === m} className={`cursor-pointer ${k === m ? "text-fg" : "text-fg-2"} hover:text-fg`} onClick={() => setMethod(k)}>
                <td className="py-1">
                  {METHOD_NAMES[k] ?? k}
                  {k === selected ? <span className="ml-1.5 text-[11px] text-accent">selected</span> : null}
                </td>
                <td className="num py-1 text-right">{fmt(r.outer.rmse, 3)}</td>
                <td className="num py-1 text-right">{fmt(r.fold_rmse_sd, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.selection?.ratio_to_idw ? <p className="num mt-1 text-[11px] text-fg-3">Selected / IDW RMSE: {fmt(data.selection.ratio_to_idw, 3)} (criterion ≤ 0.70)</p> : null}
      </div>
      <Segmented
        label="Validation chart"
        columns={3}
        value={plot}
        onChange={setPlot}
        options={[
          { value: "variogram", label: "Variogram" },
          { value: "scatter", label: "Pred. vs obs." },
          { value: "z", label: "z histogram", disabled: !rep?.points.z },
        ]}
      />
      {plot === "variogram" ? <VariogramChart v={data.variogram} accent={accent} fg={fg} fg3={fg3} /> : null}
      {plot === "scatter" && rep ? <ScatterChart rep={rep} accent={accent} fg3={fg3} /> : null}
      {plot === "z" && rep?.points.z ? <ZChart z={rep.points.z} accent={accent} fg={fg} /> : null}
      {rep ? (
        <div>
          <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Outer folds ({METHOD_NAMES[m] ?? m})</h3>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-fg-3">
                <th className="py-1 text-left font-normal">Fold</th>
                <th className="py-1 text-left font-normal">Chosen</th>
                <th className="py-1 text-right font-normal">n</th>
                <th className="py-1 text-right font-normal">RMSE</th>
                <th className="py-1 text-right font-normal">c</th>
              </tr>
            </thead>
            <tbody className="num">
              {rep.folds.map((f) => (
                <tr key={f.fold} className="text-fg-2">
                  <td className="py-1">{f.fold + 1}</td>
                  <td className="py-1 font-sans">{f.chosen}</td>
                  <td className="py-1 text-right">{f.n_test}</td>
                  <td className="py-1 text-right text-fg">{fmt(f.rmse, 2)}</td>
                  <td className="py-1 text-right">{f.calibration_c ? fmt(f.calibration_c, 2) : "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function VariogramChart({ v, accent, fg, fg3 }: { v: import("../api/types").Variogram | undefined; accent: string; fg: string; fg3: string }) {
  const traces = useMemo(() => {
    if (!v?.experimental) return [];
    const e = v.experimental;
    const maxN = Math.max(...e.n_pairs);
    const t: unknown[] = [
      {
        type: "scatter",
        mode: "markers",
        name: "experimental",
        x: e.lag_m.map((x) => x / 1000),
        y: e.gamma_mgal2,
        marker: { color: fg, size: e.n_pairs.map((n) => 4 + 8 * Math.sqrt(n / maxN)) },
        hovertemplate: "lag %{x:.1f} km<br>γ %{y:.1f} mGal²<extra></extra>",
      },
    ];
    (v.directional ?? []).forEach((d, i) =>
      t.push({ type: "scatter", mode: "lines", name: `${d.direction_deg}°`, x: d.lag_m.map((x) => x / 1000), y: d.gamma_mgal2, line: { color: fg3, width: 1, dash: ["dot", "dash", "dashdot", "longdash"][i] } }),
    );
    if (v.fitted_curve) t.push({ type: "scatter", mode: "lines", name: "fitted Matérn", x: v.fitted_curve.lag_m.map((x) => x / 1000), y: v.fitted_curve.gamma_mgal2, line: { color: accent, width: 2 } });
    return t;
  }, [v, accent, fg, fg3]);
  if (!v?.experimental) return <Empty>{v?.note ?? "No variogram for this method."}</Empty>;
  const mdl = v.model;
  return (
    <div>
      <Plot
        height={300}
        label="Experimental semivariogram of the trend residuals with the fitted Matérn model and directional variograms"
        data={traces}
        layout={{ showlegend: true, legend: { orientation: "h", y: -0.32, font: { size: 10 } }, margin: { l: 52, r: 16, t: 8, b: 78 }, xaxis: { title: { text: "Lag (km)" } }, yaxis: { title: { text: "γ (mGal²)" } } }}
      />
      {mdl ? (
        <p className="num text-[11px] text-fg-3">
          ν = {mdl.nu} · nugget {fmt(mdl.nugget, 2)} mGal² · partial sill {fmt(mdl.psill, 1)} mGal² · length {fmt(mdl.length_m / 1000, 1)} km
        </p>
      ) : null}
    </div>
  );
}

function ScatterChart({ rep, accent, fg3 }: { rep: CvReport; accent: string; fg3: string }) {
  const { observed, predicted } = rep.points;
  const lo = Math.min(...observed, ...predicted);
  const hi = Math.max(...observed, ...predicted);
  return (
    <Plot
      label={`Predicted versus observed values in block cross-validation, RMSE ${fmt(rep.outer.rmse, 2)} mGal`}
      data={[
        { type: "scatter", mode: "lines", x: [lo, hi], y: [lo, hi], line: { color: fg3, width: 1, dash: "dash" }, hoverinfo: "skip" },
        { type: "scatter", mode: "markers", x: observed, y: predicted, marker: { color: accent, size: 4, opacity: 0.6 }, hovertemplate: "obs %{x:.2f}<br>pred %{y:.2f}<extra></extra>" },
      ]}
      layout={{ xaxis: { title: { text: "Observed (mGal)" } }, yaxis: { title: { text: "Predicted (mGal)" } } }}
    />
  );
}

function ZChart({ z, accent, fg }: { z: number[]; accent: string; fg: string }) {
  const h = histogram(z, 30, -4, 4);
  const w = 8 / 30;
  const xs = Array.from({ length: 81 }, (_, i) => -4 + i * 0.1);
  const pdf = xs.map((x) => (z.length * w * Math.exp(-0.5 * x * x)) / Math.sqrt(2 * Math.PI));
  return (
    <Plot
      label="Histogram of standardized cross-validation errors with the standard normal density"
      data={[
        { type: "bar", x: h.centers, y: h.counts, marker: { color: accent, opacity: 0.7 }, hovertemplate: "z %{x:.2f}: %{y}<extra></extra>" },
        { type: "scatter", mode: "lines", x: xs, y: pdf, line: { color: fg, width: 1.5 }, hoverinfo: "skip" },
      ]}
      layout={{ bargap: 0.05, xaxis: { title: { text: "z = (obs − pred) / σ_cal" } }, yaxis: { title: { text: "Count" } } }}
    />
  );
}

export function ProfilePanel() {
  const { gridId, drawing, profileLine, set } = useUi();
  const src = useSource();
  const prof = useProfile();
  const [text, setText] = useState("");
  const [buffer, setBuffer] = useState(2000);
  const [typedError, setTypedError] = useState<string | undefined>();
  if (!gridId) return <Empty>{en.emptyGrid}</Empty>;
  if (src.mode === "static") return <Empty>{en.needsApi}</Empty>;
  const run = (coords: [number, number][]) => prof.mutate({ gridId, coordinates: coords, bufferM: buffer });
  return (
    <div className="flex flex-col gap-3">
      <Empty>{en.emptyProfile}</Empty>
      <div className="flex flex-wrap gap-2">
        <Button variant={drawing ? "primary" : "ghost"} aria-pressed={drawing} onClick={() => set({ drawing: !drawing, ...(drawing ? {} : { profileLine: [] }) })}>
          {drawing ? `Drawing (${profileLine.length} pts)` : "Draw on map"}
        </Button>
        <Button
          disabled={profileLine.length < 2 || prof.isPending}
          onClick={() => {
            set({ drawing: false });
            run(profileLine);
          }}
        >
          Compute profile
        </Button>
        <Button onClick={() => set({ profileLine: [], drawing: false })} disabled={!profileLine.length}>
          Clear
        </Button>
      </div>
      <Field label="Or type vertices (lon,lat; lon,lat)" error={typedError}>
        {(id, d) => (
          <div className="flex gap-2">
            <input id={id} aria-describedby={d} className={`${inputClass} num`} value={text} placeholder="-75.3,9.0; -74.7,9.0" onChange={(e) => setText(e.target.value)} />
            <Button
              onClick={() => {
                const pts = parseCoordinates(text);
                setTypedError(pts ? undefined : "Enter at least two lon,lat pairs separated by ';'.");
                if (pts) {
                  set({ profileLine: pts });
                  run(pts);
                }
              }}
            >
              Go
            </Button>
          </div>
        )}
      </Field>
      <Field label="Station buffer (m)">
        {(id) => <input id={id} className={`${inputClass} num`} type="number" min={0} max={20000} step={500} value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} />}
      </Field>
      {prof.isPending ? <SkeletonLines lines={5} /> : null}
      {prof.error ? <ErrorNote error={prof.error} /> : null}
      {prof.data ? <ProfileChart p={prof.data} /> : null}
    </div>
  );
}

export function ProfileChart({ p }: { p: ProfileData }) {
  const accent = themeColor("--accent", "#b45309");
  const fg = themeColor("--text", "#18181b");
  const fg3 = themeColor("--text-3", "#71717a");
  const up = p.value.map((v, i) => (v === null || p.sigma[i] === null ? null : v + 2 * (p.sigma[i] as number)));
  const lo = p.value.map((v, i) => (v === null || p.sigma[i] === null ? null : v - 2 * (p.sigma[i] as number)));
  return (
    <div data-testid="profile-chart">
      <Plot
        height={300}
        label={`Profile of ${p.length_km.toFixed(1)} km with ±2σ band and ${p.stations.length} stations within the buffer`}
        data={[
          { type: "scatter", mode: "lines", x: p.distance_km, y: lo, line: { width: 0 }, hoverinfo: "skip", connectgaps: false },
          { type: "scatter", mode: "lines", x: p.distance_km, y: up, fill: "tonexty", fillcolor: "rgba(113,113,122,0.2)", line: { width: 0 }, name: "±2σ", hoverinfo: "skip", connectgaps: false },
          { type: "scatter", mode: "lines", x: p.distance_km, y: p.value, line: { color: fg, width: 2 }, name: "grid", connectgaps: false, hovertemplate: "%{x:.1f} km: %{y:.2f} mGal<extra></extra>" },
          {
            type: "scatter",
            mode: "markers",
            x: p.stations.map((s) => s.distance_km),
            y: p.stations.map((s) => s.value),
            error_y: { type: "data", array: p.stations.map((s) => s.sigma ?? 0), visible: true, color: accent },
            marker: { color: accent, size: 6 },
            name: "stations",
            hovertemplate: "%{x:.1f} km: %{y:.2f} mGal<extra></extra>",
          },
          { type: "scatter", mode: "markers", x: p.stations.map((s) => s.distance_km), y: p.stations.map((s) => s.height_m), yaxis: "y2", marker: { color: fg3, symbol: "triangle-up", size: 5 }, name: "H", hovertemplate: "H %{y:.0f} m<extra></extra>" },
        ]}
        layout={{
          showlegend: true,
          legend: { orientation: "h", y: -0.3, font: { size: 10 } },
          margin: { l: 52, r: 48, t: 8, b: 78 },
          xaxis: { title: { text: "Distance along profile (km)" } },
          yaxis: { title: { text: "mGal" } },
          yaxis2: { title: { text: "H (m)" }, overlaying: "y", side: "right", showgrid: false },
        }}
      />
      <p className="num text-[11px] text-fg-3">
        {p.length_km.toFixed(1)} km · {p.stations.length} stations within {p.stations.length ? "the buffer" : "the buffer (none)"} · unsupported segments left blank
      </p>
    </div>
  );
}

export function DensityPanel() {
  const { dataset, densities, quantity, set } = useUi();
  const [a, setA] = useState(densities[0]);
  const [b, setB] = useState(densities[1]);
  const d = useDensity(dataset, densities, true);
  const accent = themeColor("--accent", "#b45309");
  const fg3 = themeColor("--text-3", "#71717a");
  const valid = (x: number) => x >= 1000 && x <= 3500;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
        <Field label="ρ A (kg/m³)">{(id) => <input id={id} className={`${inputClass} num`} type="number" value={a} onChange={(e) => setA(Number(e.target.value))} />}</Field>
        <Field label="ρ B (kg/m³)">{(id) => <input id={id} className={`${inputClass} num`} type="number" value={b} onChange={(e) => setB(Number(e.target.value))} />}</Field>
        <Button variant="primary" disabled={!valid(a) || !valid(b) || a === b} onClick={() => set({ densities: [a, b], quantity: "delta_cba_mgal" })}>
          Compare
        </Button>
      </div>
      {d.isLoading ? <SkeletonLines lines={6} /> : null}
      {d.error ? <ErrorNote error={d.error} /> : null}
      {d.data ? (
        <>
          <div className="grid grid-cols-3 border-y border-line">
            <Stat k={`Mean Δ CBA (${d.data.densities_kg_m3[0]}−${d.data.densities_kg_m3[1]})`} v={fmt(d.data.stats.mean, 2)} s="mGal" />
            <Stat k="Minimum" v={fmt(d.data.stats.min, 2)} s="mGal" />
            <Stat k="Maximum" v={fmt(d.data.stats.max, 2)} s="mGal" />
          </div>
          {quantity !== "delta_cba_mgal" ? (
            <Button onClick={() => set({ quantity: "delta_cba_mgal" })} className="self-start">
              Show Δ CBA on the map
            </Button>
          ) : null}
          <div>
            <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Nettleton: corr(CBA(ρ), H) after degree-2 detrending</h3>
            <Plot
              height={220}
              label="Nettleton curve: correlation between the complete Bouguer anomaly and height as a function of density"
              data={[
                { type: "scatter", mode: "lines", x: d.data.diagnostics.nettleton_curve.rho_kg_m3, y: d.data.diagnostics.nettleton_curve.corr, line: { color: accent, width: 2 } },
                { type: "scatter", mode: "lines", x: [1800, 3000], y: [0, 0], line: { color: fg3, width: 1, dash: "dot" }, hoverinfo: "skip" },
              ]}
              layout={{ xaxis: { title: { text: "ρ (kg/m³)" } }, yaxis: { title: { text: "corr" } } }}
            />
          </div>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-fg-3">
                <th className="py-1 text-left font-normal">Estimator</th>
                <th className="py-1 text-right font-normal">ρ (kg/m³)</th>
                <th className="py-1 text-right font-normal">95 % CI</th>
              </tr>
            </thead>
            <tbody className="num">
              {(["nettleton", "parasnis"] as const).map((k) => (
                <tr key={k}>
                  <td className="py-1 font-sans capitalize">{k}</td>
                  <td className="py-1 text-right">{fmt(d.data.diagnostics[k].estimate_kg_m3, 0)}</td>
                  <td className="py-1 text-right">
                    {fmt(d.data.diagnostics[k].ci95_kg_m3[0], 0)} to {fmt(d.data.diagnostics[k].ci95_kg_m3[1], 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[12px] leading-relaxed text-fg-2">
            {d.data.diagnostics.h5.supported
              ? "These data do not constrain the reduction density (H5 supported): use the standard 2670 kg/m³ and treat 2300 kg/m³ as a scenario."
              : "The density is constrained by these data (H5 not supported)."}
          </p>
        </>
      ) : null}
    </div>
  );
}
