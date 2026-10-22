import type { StationCollection, StationFeature } from "../api/types";

/** QC flags that make a station unusable (MASTER_GUIDE §5.8). */
export const ERROR_FLAGS = new Set(["ERROR_SCHEMA", "ERROR_RANGE", "CONFLICT_SHARED_ID"]);

export const QC_CATEGORIES = ["none", "warning", "TC_SUSPECT", "DUPLICATE_POSITION", "error"] as const;

/** Ordinal QC category used to colour the "QC flag" layer (0 = no flag ... 4 = error). */
export function qcCode(flags: string[]): number {
  if (flags.some((f) => ERROR_FLAGS.has(f))) return 4;
  if (flags.includes("DUPLICATE_POSITION")) return 3;
  if (flags.includes("TC_SUSPECT")) return 2;
  return flags.length ? 1 : 0;
}

/**
 * Add derived properties to every station: `delta_ref_mgal` (CBA of this run minus the
 * reference run), `delta_cba_mgal` (density sensitivity), `qc` (ordinal flag category) and
 * `flagged` (any flag, for the outlined marker). Error-flagged stations get null values so they
 * never drive colour limits.
 */
export function deriveStations(
  run: StationCollection | undefined,
  reference: StationCollection | undefined,
  densityDelta?: Map<string, number>,
): StationCollection | undefined {
  if (!run) return undefined;
  const ref = new Map<string, number>();
  for (const f of reference?.features ?? []) {
    const v = f.properties.cba_mgal;
    if (typeof v === "number") ref.set(f.properties.station_uid, v);
  }
  const features: StationFeature[] = run.features.map((f) => {
    const p = f.properties;
    const err = p.qc_flags.some((x) => ERROR_FLAGS.has(x));
    const cba = typeof p.cba_mgal === "number" ? p.cba_mgal : null;
    const r = ref.get(p.station_uid);
    const out: Record<string, unknown> = {
      ...p,
      qc: qcCode(p.qc_flags),
      flagged: p.qc_flags.length > 0 ? 1 : 0,
      delta_ref_mgal: cba !== null && r !== undefined ? cba - r : null,
      delta_cba_mgal: densityDelta?.get(p.station_uid) ?? null,
    };
    if (err) for (const k of ["faa_mgal", "sba_mgal", "cba_mgal", "cba_residual_mgal", "delta_ref_mgal", "delta_cba_mgal"]) out[k] = null;
    return { ...f, properties: out as StationFeature["properties"] };
  });
  return { ...run, features };
}

export function values(fc: StationCollection | undefined, key: string): number[] {
  const out: number[] = [];
  for (const f of fc?.features ?? []) {
    const v = f.properties[key];
    if (typeof v === "number" && Number.isFinite(v)) out.push(v);
  }
  return out;
}

/** Histogram with fixed-width bins. */
export function histogram(xs: number[], bins: number, lo: number, hi: number): { centers: number[]; counts: number[] } {
  const w = (hi - lo) / bins;
  const counts = new Array<number>(bins).fill(0);
  for (const x of xs) {
    if (!Number.isFinite(x) || x < lo || x > hi) continue;
    const i = Math.min(bins - 1, Math.floor((x - lo) / w));
    counts[i] = (counts[i] ?? 0) + 1;
  }
  return { centers: counts.map((_, i) => lo + w * (i + 0.5)), counts };
}

/** Parse "lon,lat; lon,lat" (keyboard alternative to drawing a profile). */
export function parseCoordinates(text: string): [number, number][] | null {
  const parts = text.split(";").map((s) => s.trim()).filter(Boolean);
  const pts: [number, number][] = [];
  for (const p of parts) {
    const nums = p.split(/[,\s]+/).map(Number);
    if (nums.length !== 2 || nums.some((n) => !Number.isFinite(n))) return null;
    const [lon, lat] = nums as [number, number];
    if (Math.abs(lon) > 180 || Math.abs(lat) > 90) return null;
    pts.push([lon, lat]);
  }
  return pts.length >= 2 ? pts : null;
}
