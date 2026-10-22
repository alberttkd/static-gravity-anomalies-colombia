import { CMAPS, cssGradient, fmt, ticks, type CmapName } from "../lib/colormaps";
import { QC_CATEGORIES } from "../lib/derive";

const QC_COLORS = ["#a1a1aa", "#2a788e", "#7ad151", "#355f8d", "#b2182b"];

export function Legend({
  title,
  units,
  limits,
  cmap,
  categorical,
}: {
  title: string;
  units: string;
  limits: [number, number];
  cmap: CmapName;
  categorical?: boolean;
}) {
  return (
    <figure className="w-[268px] rounded-[6px] border border-line bg-surface px-3 py-2.5" aria-label={`Legend: ${title}`}>
      <figcaption className="mb-2 text-[12px] font-semibold">
        {title} {units ? <span className="font-normal text-fg-3">({units})</span> : null}
      </figcaption>
      {categorical ? (
        <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-fg-2">
          {QC_CATEGORIES.map((c, i) => (
            <li key={c} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: QC_COLORS[i] }} aria-hidden />
              {c === "none" ? "No flag" : c === "warning" ? "Warning" : c === "error" ? "Error (excluded)" : c}
            </li>
          ))}
        </ul>
      ) : (
        <>
          <div className="h-2.5 rounded-[2px]" style={{ background: cssGradient(cmap) }} aria-hidden data-stops={CMAPS[cmap].length} />
          <div className="num mt-1 flex justify-between text-[11px] text-fg-2">
            {ticks(limits[0], limits[1]).map((t, i) => (
              <span key={i}>{fmt(t, Math.abs(limits[1] - limits[0]) < 10 ? 1 : 0)}</span>
            ))}
          </div>
        </>
      )}
    </figure>
  );
}
