import { useEffect, useState } from "react";
import { useJob, useSource, useSubmitGrid } from "../api/hooks";
import type { GriddingConfig, ReductionConfig } from "../api/types";
import { en } from "../i18n/en";
import { DEFAULT_REDUCTION, useUi, type GridLayer, type Quantity } from "../state/store";
import { Button, ErrorNote, Field, Section, Segmented, Switch, inputClass } from "./ui";

export function LayerPanel({ hasDensity }: { hasDensity: boolean }) {
  const { quantity, set } = useUi();
  const opt = (v: Quantity, disabled = false) => ({ value: v, label: en.quantities[v] ?? v, disabled });
  return (
    <Section title="Station layer">
      <Segmented label="Station quantity" value={quantity} onChange={(v) => set({ quantity: v })} options={[opt("faa_mgal"), opt("sba_mgal"), opt("cba_mgal"), opt("cba_residual_mgal")]} />
      <Segmented label="Station quantity (other)" columns={3} value={quantity} onChange={(v) => set({ quantity: v })} options={[opt("height_m"), opt("sigma_cba_mgal"), opt("qc")]} />
      <Segmented label="Differences" columns={2} value={quantity} onChange={(v) => set({ quantity: v })} options={[opt("delta_ref_mgal"), opt("delta_cba_mgal", !hasDensity)]} />
    </Section>
  );
}

export function ReductionPanel() {
  const { reduction, set } = useUi();
  const src = useSource();
  const [draft, setDraft] = useState<Partial<ReductionConfig>>(reduction);
  const rho = Number(draft.density_kg_m3);
  const rhoError = !Number.isFinite(rho) || rho < 1000 || rho > 3500 ? "Enter a density between 1000 and 3500 kg/m³." : undefined;
  const staticBlocked = src.mode === "static" && (draft.legacy_mode || draft.honkasalo === false || draft.atmospheric === false || draft.curvature !== "lafehr1991_closed_form" || (rho !== 2670 && rho !== 2300));
  const dirty = JSON.stringify(draft) !== JSON.stringify(reduction);
  const up = (p: Partial<ReductionConfig>) => setDraft((d) => ({ ...d, ...p }));
  return (
    <Section title="Reduction">
      <Field label="Bouguer density (kg/m³)" help="Reference 2670; legacy value 2300." error={rhoError}>
        {(id, d) => (
          <input
            id={id}
            aria-describedby={d}
            aria-invalid={!!rhoError}
            className={`${inputClass} num`}
            type="number"
            inputMode="decimal"
            step={10}
            value={draft.density_kg_m3 ?? ""}
            onChange={(e) => up({ density_kg_m3: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
          />
        )}
      </Field>
      <Field label="Curvature (Bullard B)">
        {(id) => (
          <select id={id} className={inputClass} value={draft.curvature} onChange={(e) => up({ curvature: e.target.value as ReductionConfig["curvature"] })}>
            <option value="lafehr1991_closed_form">LaFehr (1991) closed form</option>
            <option value="supplied_bb_legacy">Supplied BB (legacy, audit only)</option>
            <option value="none">None (planar slab)</option>
          </select>
        )}
      </Field>
      <div>
        <Switch label="Honkasalo term" checked={draft.honkasalo ?? true} onChange={(v) => up({ honkasalo: v })} />
        <Switch label="Atmospheric correction" checked={draft.atmospheric ?? true} onChange={(v) => up({ atmospheric: v })} />
        <Switch label="Legacy mode (legacy spreadsheets)" checked={draft.legacy_mode ?? false} onChange={(v) => up({ legacy_mode: v })} />
      </div>
      {staticBlocked ? <p className="text-[11px] text-fg-3">{en.needsApi}</p> : null}
      <div className="grid grid-cols-[1fr_auto] gap-2">
        <Button variant="primary" disabled={!!rhoError || !dirty || staticBlocked} onClick={() => set({ reduction: draft, selected: null })}>
          Run reduction
        </Button>
        <Button
          onClick={() => {
            setDraft(DEFAULT_REDUCTION);
            set({ reduction: DEFAULT_REDUCTION });
          }}
        >
          Reset
        </Button>
      </div>
    </Section>
  );
}

export function GriddingPanel() {
  const { runId, jobId, set } = useUi();
  const src = useSource();
  const submit = useSubmitGrid();
  const job = useJob(jobId);
  const [cfg, setCfg] = useState<Partial<GriddingConfig>>({ method: "auto", target: "CBA", cell_size_m: 500, mask: { max_distance_m: 5000, use_convex_hull: true, max_sigma_mgal: 5 } });
  const status = job.data?.status;
  const busy = submit.isPending || status === "queued" || status === "running";

  useEffect(() => {
    if (job.data?.status === "done" && job.data.grid_id) set({ gridId: job.data.grid_id });
  }, [job.data, set]);

  return (
    <Section title="Gridding">
      <Field label="Method" help="Auto selects by nested spatial block cross-validation.">
        {(id, d) => (
          <select id={id} aria-describedby={d} className={inputClass} value={cfg.method} disabled={src.mode === "static"} onChange={(e) => setCfg((c) => ({ ...c, method: e.target.value as GriddingConfig["method"] }))}>
            <option value="auto">Auto (block CV)</option>
            <option value="rk_matern">Regression kriging (Matérn)</option>
            <option value="eqs">Equivalent sources</option>
            <option value="idw">IDW (baseline)</option>
            <option value="spline">Spline (baseline)</option>
          </select>
        )}
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Target">
          {(id) => (
            <select id={id} className={inputClass} value={cfg.target} disabled={src.mode === "static"} onChange={(e) => setCfg((c) => ({ ...c, target: e.target.value as GriddingConfig["target"] }))}>
              <option value="CBA">CBA</option>
              <option value="SBA">SBA</option>
              <option value="FAA">FAA</option>
              <option value="residual">Residual</option>
            </select>
          )}
        </Field>
        <Field label="Cell (m)">
          {(id) => (
            <input id={id} className={`${inputClass} num`} type="number" min={100} max={5000} step={50} value={cfg.cell_size_m} disabled={src.mode === "static"} onChange={(e) => setCfg((c) => ({ ...c, cell_size_m: Number(e.target.value) }))} />
          )}
        </Field>
      </div>
      <Field label="Mask: max distance to a station (m)" help="Cells farther away, or outside the hull, stay transparent.">
        {(id, d) => (
          <input
            id={id}
            aria-describedby={d}
            className={`${inputClass} num`}
            type="number"
            min={1000}
            max={20000}
            step={500}
            value={cfg.mask?.max_distance_m}
            disabled={src.mode === "static"}
            onChange={(e) => setCfg((c) => ({ ...c, mask: { ...(c.mask as NonNullable<GriddingConfig["mask"]>), max_distance_m: Number(e.target.value) } }))}
          />
        )}
      </Field>
      <Button
        variant="primary"
        disabled={!runId || busy}
        onClick={() =>
          runId &&
          submit.mutate(
            { runId, config: cfg },
            { onSuccess: (j) => set({ jobId: j.job_id, ...(j.status === "done" && j.grid_id ? { gridId: j.grid_id } : {}) }) },
          )
        }
      >
        {busy ? `Gridding ${Math.round((job.data?.progress ?? 0) * 100)} %` : src.mode === "static" ? "Show precomputed grid" : "Run gridding"}
      </Button>
      {busy ? (
        <div className="h-1 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Math.round((job.data?.progress ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Gridding progress">
          <div className="h-full bg-accent transition-transform duration-300" style={{ transform: `scaleX(${job.data?.progress ?? 0.02})`, transformOrigin: "left" }} />
        </div>
      ) : null}
      {submit.error ? <ErrorNote error={submit.error} /> : null}
      {status === "failed" && job.data?.error ? <ErrorNote error={new Error(`${job.data.error.detail} (${job.data.error.code})`)} /> : null}
    </Section>
  );
}

export function GridDisplayPanel() {
  const { gridId, gridLayer, showGrid, showContours, showHatch, opacity, set } = useUi();
  if (!gridId) return null;
  return (
    <Section title="Grid layer">
      <Segmented<GridLayer>
        label="Grid layer"
        value={gridLayer}
        onChange={(v) => set({ gridLayer: v })}
        options={(["value", "sigma_cal", "trend", "residual"] as GridLayer[]).map((v) => ({ value: v, label: en.gridLayers[v] ?? v }))}
      />
      <div>
        <Switch label="Show grid" checked={showGrid} onChange={(v) => set({ showGrid: v })} />
        <Switch label={gridLayer === "residual" ? "Contours (1 mGal)" : "Contours (5 mGal)"} checked={showContours} onChange={(v) => set({ showContours: v })} />
        <Switch label="Hatch σ > 5 mGal" checked={showHatch} onChange={(v) => set({ showHatch: v })} />
      </div>
      <Field label={`Opacity ${Math.round(opacity * 100)} %`}>
        {(id) => <input id={id} type="range" min={0.2} max={1} step={0.05} value={opacity} onChange={(e) => set({ opacity: Number(e.target.value) })} className="accent-[var(--accent)]" />}
      </Field>
    </Section>
  );
}
