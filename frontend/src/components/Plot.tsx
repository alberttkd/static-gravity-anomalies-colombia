/** Lazy Plotly wrapper (plotly.js-basic: scatter + bar). Colours follow the current theme tokens. */
import { useEffect, useRef } from "react";

type PlotlyModule = {
  react: (el: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>;
  purge: (el: HTMLElement) => void;
};

let plotlyPromise: Promise<PlotlyModule> | null = null;
function loadPlotly(): Promise<PlotlyModule> {
  plotlyPromise ??= import("plotly.js-basic-dist-min").then((m) => (m as { default: PlotlyModule }).default);
  return plotlyPromise;
}

export function themeColor(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export function Plot({
  data,
  layout,
  height = 260,
  label,
}: {
  data: unknown[];
  layout: Record<string, unknown>;
  height?: number;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    const el = ref.current;
    if (!el) return;
    const text = themeColor("--text-2", "#52525b");
    const line = themeColor("--line", "#e4e4e7");
    const fullLayout = {
      height,
      margin: { l: 52, r: 16, t: 8, b: 40 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Geist Variable, sans-serif", size: 11, color: text },
      showlegend: false,
      ...layout,
      xaxis: { gridcolor: line, zerolinecolor: line, linecolor: line, ...(layout.xaxis as object) },
      yaxis: { gridcolor: line, zerolinecolor: line, linecolor: line, ...(layout.yaxis as object) },
    };
    loadPlotly()
      .then((P) => {
        if (!cancelled) return P.react(el, data, fullLayout, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
      })
      .catch(() => {
        /* rendering failure leaves the accessible summary in place */
      });
    return () => {
      cancelled = true;
    };
  }, [data, layout, height]);
  return <div ref={ref} role="img" aria-label={label} style={{ height }} className="w-full" />;
}
