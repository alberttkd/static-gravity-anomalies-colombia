/**
 * Colour maps for data. Both are colour-blind safe:
 * - RdBu (ColorBrewer, diverging) for anomalies, centred at 0 mGal with symmetric limits;
 * - viridis (sequential, perceptually uniform) for heights and uncertainties.
 * The UI accent colour is never used to encode data.
 */

export type CmapName = "RdBu_r" | "viridis";

// ColorBrewer RdBu (11 classes), reversed so that negative = blue, positive = red.
const RDBU_R = [
  "#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7",
  "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f",
];
// viridis sampled at 11 points.
const VIRIDIS = [
  "#440154", "#482475", "#414487", "#355f8d", "#2a788e", "#21918c",
  "#22a884", "#44bf70", "#7ad151", "#bddf26", "#fde725",
];

export const CMAPS: Record<CmapName, string[]> = { RdBu_r: RDBU_R, viridis: VIRIDIS };

/** Quantities shown with the diverging map (signed anomalies). */
export const DIVERGING = new Set(["faa_mgal", "sba_mgal", "cba_mgal", "cba_residual_mgal", "delta_cba_mgal", "delta_ref_mgal"]);

export function cmapFor(quantity: string): CmapName {
  return DIVERGING.has(quantity) ? "RdBu_r" : "viridis";
}

export function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  const a = sorted[lo] ?? NaN;
  const b = sorted[hi] ?? NaN;
  return a + (b - a) * (pos - lo);
}

function finiteSorted(values: Iterable<number | null | undefined>): number[] {
  const out: number[] = [];
  for (const v of values) if (typeof v === "number" && Number.isFinite(v)) out.push(v);
  return out.sort((x, y) => x - y);
}

/** Symmetric limits (-a, a) from the robust 2-98 % range, centred at 0. */
export function symmetricLimits(values: Iterable<number | null | undefined>): [number, number] {
  const s = finiteSorted(values);
  if (s.length === 0) return [-1, 1];
  const a = Math.max(Math.abs(quantile(s, 0.02)), Math.abs(quantile(s, 0.98))) || 1;
  return [-a, a];
}

/** Sequential limits from the robust 2-98 % range. */
export function sequentialLimits(values: Iterable<number | null | undefined>): [number, number] {
  const s = finiteSorted(values);
  if (s.length === 0) return [0, 1];
  const lo = quantile(s, 0.02);
  const hi = quantile(s, 0.98);
  return hi > lo ? [lo, hi] : [lo, lo + 1];
}

export function limitsFor(quantity: string, values: Iterable<number | null | undefined>): [number, number] {
  return cmapFor(quantity) === "RdBu_r" ? symmetricLimits(values) : sequentialLimits(values);
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Colour for a value (linear interpolation between stops; clamped). */
export function colorAt(value: number, vmin: number, vmax: number, cmap: CmapName): string {
  const stops = CMAPS[cmap];
  const t = Math.min(1, Math.max(0, vmax > vmin ? (value - vmin) / (vmax - vmin) : 0.5));
  const pos = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(pos));
  const f = pos - i;
  const a = hexToRgb(stops[i] ?? "#000000");
  const b = hexToRgb(stops[i + 1] ?? "#000000");
  const c = a.map((x, k) => Math.round(x + ((b[k] ?? 0) - x) * f));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** MapLibre `interpolate` expression for a numeric feature property. */
export function interpolateExpression(property: string, vmin: number, vmax: number, cmap: CmapName): unknown[] {
  const stops = CMAPS[cmap];
  const expr: unknown[] = ["interpolate", ["linear"], ["to-number", ["get", property]]];
  stops.forEach((color, i) => {
    expr.push(vmin + ((vmax - vmin) * i) / (stops.length - 1), color);
  });
  return expr;
}

/** CSS linear-gradient for colour bars. */
export function cssGradient(cmap: CmapName): string {
  return `linear-gradient(90deg, ${CMAPS[cmap].join(", ")})`;
}

/** Nice tick values between limits (5 ticks). */
export function ticks(vmin: number, vmax: number, n = 5): number[] {
  return Array.from({ length: n }, (_, i) => vmin + ((vmax - vmin) * i) / (n - 1));
}

export function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  return v.toFixed(digits).replace("-", "−");
}
