import type { ReactNode } from "react";
import { useManifest, useQc } from "../api/hooks";
import type { StationCollection } from "../api/types";
import { en } from "../i18n/en";
import { fmt } from "../lib/colormaps";
import { useUi, type InspectorTab } from "../state/store";
import { DensityPanel, ProfilePanel, ValidationPanel } from "./Charts";
import { Empty, ErrorNote, SkeletonLines, Stat } from "./ui";

const TABS: InspectorTab[] = ["station", "validation", "profile", "qc", "density", "provenance"];

export function Inspector({ stations }: { stations?: StationCollection }) {
  const { tab, set } = useUi();
  return (
    <div className="flex min-h-0 flex-col">
      <div role="tablist" aria-label="Inspector" className="flex h-[42px] shrink-0 gap-4 overflow-x-auto border-b border-line px-4">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            id={`tab-${t}`}
            aria-selected={tab === t}
            aria-controls={`panel-${t}`}
            onClick={() => set({ tab: t })}
            className={`border-b-2 text-[13px] whitespace-nowrap transition-colors ${tab === t ? "border-accent font-semibold text-fg" : "border-transparent text-fg-3 hover:text-fg"}`}
          >
            {en.tabs[t]}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "station" ? <StationPanel stations={stations} /> : null}
        {tab === "validation" ? <ValidationPanel /> : null}
        {tab === "profile" ? <ProfilePanel /> : null}
        {tab === "qc" ? <QCPanel /> : null}
        {tab === "density" ? <DensityPanel /> : null}
        {tab === "provenance" ? <ProvenancePanel /> : null}
      </div>
    </div>
  );
}

const n = (v: unknown) => (typeof v === "number" ? v : null);

function Row({ label, value, total, sign = "" }: { label: string; value: unknown; total?: boolean; sign?: string }) {
  const v = n(value);
  const txt = v === null ? "n/a" : `${sign && v >= 0 ? sign : ""}${fmt(v, 3)}`;
  return (
    <tr className={total ? "border-t border-line font-semibold text-fg" : "text-fg-2"}>
      <td className={`py-1.5 ${total ? "pt-2" : ""}`}>{label}</td>
      <td className={`num py-1.5 text-right text-fg ${total ? "pt-2" : ""}`}>{txt}</td>
    </tr>
  );
}

export function StationPanel({ stations }: { stations?: StationCollection }) {
  const { selected } = useUi();
  if (!stations) return <SkeletonLines lines={6} />;
  const f = stations.features.find((x) => x.properties.station_uid === selected);
  if (!f) return <Empty>{en.emptyStation}</Empty>;
  const p = f.properties;
  const neg = (v: unknown) => (typeof v === "number" ? -v : null);
  return (
    <div className="fade-in flex flex-col gap-4">
      <div>
        <div className="num text-[14px] font-semibold break-all">{p.station_uid}</div>
        <div className="num mt-0.5 text-[12px] text-fg-3">
          {fmt(n(p.lon), 4)}, {fmt(n(p.lat), 4)} · H {fmt(n(p.height_m), 1)} m{n(p.n_merged) && (p.n_merged as number) > 1 ? ` · merged ×${p.n_merged}` : ""}
        </div>
      </div>
      <div className="grid grid-cols-3 border-y border-line">
        <Stat k="FAA" v={fmt(n(p.faa_mgal))} s={`± ${fmt(n(p.sigma_faa_mgal))}`} />
        <Stat k="SBA" v={fmt(n(p.sba_mgal))} s={`± ${fmt(n(p.sigma_sba_mgal))}`} />
        <Stat k="CBA" v={fmt(n(p.cba_mgal))} s={`± ${fmt(n(p.sigma_cba_mgal))}`} />
      </div>
      <div>
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Reduction breakdown (mGal)</h3>
        <table className="w-full text-[12px]">
          <tbody>
            <Row label="Observed g" value={p.g_obs_mgal} />
            <Row label="Normal gravity γ₀ (GRS80)" value={neg(p.gamma0_mgal)} />
            <Row label="Honkasalo term" value={p.honkasalo_mgal} sign="+" />
            <Row label="Height correction" value={p.height_corr_mgal} sign="+" />
            <Row label="Atmospheric correction" value={p.atm_mgal} sign="+" />
            <Row label="Free-air anomaly" value={p.faa_mgal} total />
            <Row label="Slab (Bullard A)" value={neg(p.bc_slab_mgal)} />
            <Row label="Simple Bouguer anomaly" value={p.sba_mgal} total />
            <Row label="Curvature BB (Bullard B)" value={neg(p.bb_mgal)} />
            <Row label="Terrain, scaled by ρ/ρ_TC (Bullard C)" value={p.tc_rho_mgal} sign="+" />
            <Row label="Complete Bouguer anomaly" value={p.cba_mgal} total />
          </tbody>
        </table>
      </div>
      <div>
        <h3 className="mb-1.5 text-[12px] font-semibold text-fg-2">QC flags</h3>
        <div className="flex flex-wrap gap-1.5">
          {(p.qc_flags.length ? p.qc_flags : ["none"]).map((fl) => (
            <span key={fl} className="rounded-[4px] border border-line px-1.5 py-0.5 text-[11px] text-fg-2">
              {fl}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-[12px]">
      <span className="text-fg-2">{k}</span>
      <span className="num text-right">{v}</span>
    </div>
  );
}

export function QCPanel() {
  const { dataset } = useUi();
  const qc = useQc(dataset);
  if (qc.isLoading) return <SkeletonLines lines={8} />;
  if (qc.error) return <ErrorNote error={qc.error} retry={() => void qc.refetch()} />;
  const r = qc.data as {
    n_stations: number;
    flag_counts: Record<string, number>;
    harmonization: {
      n_records_in?: number;
      n_shared_ids?: number;
      n_shared_consistent?: number;
      n_positions?: number;
      n_merged_groups?: number;
      merged_groups?: { station_uid: string; members: string[]; g_spread_mgal: number }[];
      repeat_precision_sigma_g_mgal?: number | null;
    };
    bb_comparison?: { per_source: Record<string, { ratio_median: number; n: number }> } | null;
  };
  const blob = URL.createObjectURL(new Blob([JSON.stringify(qc.data, null, 2)], { type: "application/json" }));
  const h = r.harmonization ?? {};
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Flags ({r.n_stations} positions)</h3>
        <table className="w-full text-[12px]">
          <tbody>
            {Object.entries(r.flag_counts).map(([k, v]) => (
              <tr key={k} className={v ? "text-fg" : "text-fg-3"}>
                <td className="py-1">{k}</td>
                <td className="num py-1 text-right">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-line pt-3">
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Harmonization</h3>
        <KV k="Input records" v={h.n_records_in ?? "n/a"} />
        <KV k="Shared ids (consistent)" v={`${h.n_shared_ids ?? 0} (${h.n_shared_consistent ?? 0})`} />
        <KV k="Positions after merging" v={h.n_positions ?? "n/a"} />
        <KV k="Duplicate groups" v={h.n_merged_groups ?? 0} />
        <KV k="σ_g from repeat pairs" v={h.repeat_precision_sigma_g_mgal ? `${fmt(h.repeat_precision_sigma_g_mgal, 2)} mGal` : "n/a"} />
      </div>
      {h.merged_groups?.length ? (
        <div className="border-t border-line pt-3">
          <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Duplicate groups</h3>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-fg-3">
                <th className="py-1 text-left font-normal">Members</th>
                <th className="py-1 text-right font-normal">g spread (mGal)</th>
              </tr>
            </thead>
            <tbody>
              {h.merged_groups.map((g) => (
                <tr key={g.station_uid}>
                  <td className="num py-1 break-all">{g.members.join(", ")}</td>
                  <td className="num py-1 text-right">{fmt(g.g_spread_mgal, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {r.bb_comparison ? (
        <div className="border-t border-line pt-3">
          <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Supplied BB / recomputed BB (audit)</h3>
          {Object.entries(r.bb_comparison.per_source).map(([s, v]) => (
            <KV key={s} k={`${s} (n = ${v.n})`} v={fmt(v.ratio_median, 3)} />
          ))}
        </div>
      ) : null}
      <a className="press self-start rounded-[6px] border border-line px-3 py-1.5 text-[13px] text-fg-2 hover:text-fg" href={blob} download={`qc_report_${dataset}.json`}>
        Download QC report (JSON)
      </a>
    </div>
  );
}

export function ProvenancePanel() {
  const { runId } = useUi();
  const m = useManifest(runId);
  if (!runId || m.isLoading) return <SkeletonLines lines={6} />;
  if (m.error) return <ErrorNote error={m.error} />;
  const man = m.data as {
    run_id: string;
    label: string;
    config_hash: string;
    inputs: Record<string, string>;
    versions: Record<string, string>;
    seeds: Record<string, number>;
    git_commit?: string | null;
    started_utc?: string;
    config: Record<string, unknown>;
  };
  return (
    <div className="flex flex-col gap-4" data-testid="provenance">
      <div>
        <KV k="Run" v={man.run_id} />
        <KV k="Dataset" v={man.label} />
        <KV k="Config hash" v={man.config_hash ? man.config_hash.slice(0, 16) : "n/a"} />
        <KV k="Git commit" v={man.git_commit ? man.git_commit.slice(0, 12) : "n/a"} />
        <KV k="Started (UTC)" v={man.started_utc ?? "n/a"} />
      </div>
      <div className="border-t border-line pt-3">
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Input hashes (SHA-256)</h3>
        {Object.entries(man.inputs ?? {}).map(([k, v]) => (
          <KV key={k} k={k} v={`${v.slice(0, 12)}…`} />
        ))}
      </div>
      <div className="border-t border-line pt-3">
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Seeds</h3>
        {Object.entries(man.seeds ?? {}).map(([k, v]) => (
          <KV key={k} k={k} v={v} />
        ))}
      </div>
      <div className="border-t border-line pt-3">
        <h3 className="mb-1 text-[12px] font-semibold text-fg-2">Versions</h3>
        {Object.entries(man.versions ?? {}).map(([k, v]) => (
          <KV key={k} k={k} v={v} />
        ))}
      </div>
      <details className="border-t border-line pt-3 text-[12px]">
        <summary className="cursor-pointer font-semibold text-fg-2">Resolved configuration</summary>
        <pre className="num mt-2 overflow-x-auto text-[11px] leading-relaxed text-fg-2">{JSON.stringify(man.config, null, 2)}</pre>
      </details>
      <div className="border-t border-line pt-3 text-[12px] text-fg-2">
        <h3 className="mb-1 font-semibold">Method references</h3>
        <ul className="list-disc space-y-1 pl-4">
          <li>Hinze et al. (2005), Geophysics 70(4), J25-J32. Reduction standard.</li>
          <li>LaFehr (1991), Geophysics 56(8), 1179-1184. Spherical cap (Bullard B).</li>
          <li>Moritz (2000), J. Geodesy 74, 128-133. GRS80.</li>
          <li>Cressie (1985); Stein (1999). Variogram fitting, Matérn covariance.</li>
          <li>Roberts et al. (2017), Ecography 40, 913-929. Block cross-validation.</li>
          <li>Software: Harmonica, Verde, Boule (Fatiando a Terra), GSTools, MapLibre.</li>
        </ul>
      </div>
    </div>
  );
}
