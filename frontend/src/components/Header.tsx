import { DownloadSimple, Moon, Sun, Desktop } from "@phosphor-icons/react";
import { useState } from "react";
import { useDatasets, useSource } from "../api/hooks";
import { en } from "../i18n/en";
import { useUi, type Theme } from "../state/store";
import { Button, inputClass } from "./ui";

const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };

export function Header() {
  const ds = useDatasets();
  const src = useSource();
  const { dataset, theme, runId, gridId, gridLayer, set } = useUi();
  const [exportOpen, setExportOpen] = useState(false);
  const current = ds.data?.find((d) => d.id === dataset);
  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : Desktop;
  const links: { label: string; href: string | null }[] = runId
    ? [
        { label: "Stations (CSV)", href: src.downloadUrl("stations", runId, "csv") },
        { label: "Stations (GeoPackage)", href: src.downloadUrl("stations", runId, "gpkg") },
        { label: "Stations (GeoParquet)", href: src.downloadUrl("stations", runId, "parquet") },
        { label: "Stations (GeoJSON)", href: src.downloadUrl("stations", runId, "geojson") },
        ...(gridId
          ? [
              { label: `Grid ${gridLayer} (COG GeoTIFF)`, href: src.downloadUrl("grid", gridId, "cog", gridLayer) },
              { label: `Grid ${gridLayer} (NetCDF)`, href: src.downloadUrl("grid", gridId, "netcdf", gridLayer) },
            ]
          : []),
      ]
    : [];

  return (
    <header className="relative z-20 flex h-[52px] items-center gap-3 border-b border-line bg-surface px-4">
      <h1 className="text-[15px] font-semibold tracking-tight whitespace-nowrap">
        {en.appName} <span className="hidden font-normal text-fg-3 lg:inline">{en.tagline}</span>
      </h1>
      <label className="flex items-center gap-2 text-[12px] text-fg-2">
        <span className="sr-only sm:not-sr-only">{en.dataset}</span>
        <select
          aria-label={en.dataset}
          className={`${inputClass} w-auto`}
          value={dataset}
          onChange={(e) => set({ dataset: e.target.value, runId: null, referenceRunId: null, gridId: null, jobId: null, selected: null })}
        >
          {(ds.data ?? [{ id: "synthetic", label: "SYNTHETIC" }]).map((d) => (
            <option key={d.id} value={d.id}>
              {d.id === "synthetic" ? "Synthetic" : "Private (real data)"}
            </option>
          ))}
        </select>
      </label>
      {current ? (
        <span
          data-testid="dataset-badge"
          className={`flex h-6 items-center rounded-[6px] border px-2 text-[11px] font-semibold tracking-wide ${
            current.kind === "synthetic" ? "border-accent bg-accent-soft text-accent" : "border-danger text-danger"
          }`}
        >
          {current.kind === "synthetic" ? en.synthetic : en.privateData}
        </span>
      ) : null}
      {src.mode === "static" ? <span className="hidden text-[12px] text-fg-3 md:inline">{en.staticMode}</span> : null}
      <div className="flex-1" />
      <div className="relative">
        <Button onClick={() => setExportOpen((v) => !v)} aria-expanded={exportOpen} aria-haspopup="menu" disabled={!runId}>
          <DownloadSimple size={15} aria-hidden /> Export
        </Button>
        {exportOpen ? (
          <div role="menu" className="fade-in absolute right-0 mt-1 w-64 origin-top-right rounded-[6px] border border-line bg-surface p-1 shadow-lg shadow-black/5">
            {src.mode === "static" ? <p className="p-2 text-[12px] text-fg-3">{en.needsApi}</p> : null}
            {links.map((l) =>
              l.href ? (
                <a key={l.label} role="menuitem" href={l.href} className="block rounded-[4px] px-2 py-1.5 text-[13px] hover:bg-surface-2" onClick={() => setExportOpen(false)}>
                  {l.label}
                </a>
              ) : null,
            )}
          </div>
        ) : null}
      </div>
      <Button onClick={() => set({ tab: "provenance" })}>Provenance</Button>
      <Button aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`} onClick={() => set({ theme: NEXT[theme] })}>
        <ThemeIcon size={15} aria-hidden />
      </Button>
    </header>
  );
}
