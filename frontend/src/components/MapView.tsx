import maplibregl, { type GeoJSONSource, type ImageSource, type Map as MlMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import type { LayerImage, StationCollection } from "../api/types";
import { interpolateExpression, type CmapName } from "../lib/colormaps";
import { themeColor } from "./Plot";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const QC_COLORS = ["#a1a1aa", "#2a788e", "#7ad151", "#355f8d", "#b2182b"];

export interface MapViewProps {
  stations?: StationCollection;
  colorProperty: string;
  limits: [number, number];
  cmap: CmapName;
  categorical?: boolean;
  selected: string | null;
  onSelect: (uid: string | null) => void;
  extent?: [number, number, number, number];
  gridImage?: LayerImage;
  hatchImage?: LayerImage;
  showGrid: boolean;
  opacity: number;
  contours?: GeoJSON.FeatureCollection;
  drawing: boolean;
  profileLine: [number, number][];
  onAddVertex: (p: [number, number]) => void;
  themeKey: string;
}

function corners(b: [number, number, number, number]): [[number, number], [number, number], [number, number], [number, number]] {
  const [w, s, e, n] = b;
  return [[w, n], [e, n], [e, s], [w, s]];
}

function stationColor(p: MapViewProps): unknown {
  if (p.categorical) return ["match", ["get", "qc"], ...QC_COLORS.flatMap((c, i) => [i, c]), QC_COLORS[0]];
  return ["case", ["==", ["get", p.colorProperty], null], themeColor("--text-3", "#71717a"), interpolateExpression(p.colorProperty, p.limits[0], p.limits[1], p.cmap)];
}

/** Map: Natural Earth basemap, stations, grid image + hatch, contours, profile line. */
export function MapView(props: MapViewProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);
  const latest = useRef(props);
  latest.current = props;

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      attributionControl: false,
      style: {
        version: 8,
        sources: { countries: { type: "geojson", data: `${import.meta.env.BASE_URL}ne_admin0_region.geojson` } },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": themeColor("--surface-2", "#f4f4f5") } },
          { id: "land", type: "fill", source: "countries", paint: { "fill-color": themeColor("--surface", "#ffffff") } },
          { id: "borders", type: "line", source: "countries", paint: { "line-color": themeColor("--line", "#e4e4e7"), "line-width": 1 } },
        ],
      },
      bounds: props.extent ?? [-76.2, 7.6, -73.4, 10.2],
      fitBoundsOptions: { padding: 40 },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    m.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Natural Earth (public domain)" }));
    m.on("load", () => {
      m.addSource("grid", { type: "image", url: transparentPixel, coordinates: corners([-76, 7, -73, 10]) });
      m.addLayer({ id: "grid", type: "raster", source: "grid", paint: { "raster-opacity": 0, "raster-resampling": "nearest" } });
      m.addSource("hatch", { type: "image", url: transparentPixel, coordinates: corners([-76, 7, -73, 10]) });
      m.addLayer({ id: "hatch", type: "raster", source: "hatch", paint: { "raster-opacity": 0, "raster-resampling": "nearest" } });
      m.addSource("contours", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "contours", type: "line", source: "contours", paint: { "line-color": themeColor("--text-2", "#52525b"), "line-width": 0.8, "line-opacity": 0.7 } });
      m.addSource("stations", { type: "geojson", data: EMPTY, promoteId: "station_uid" });
      m.addLayer({
        id: "stations",
        type: "circle",
        source: "stations",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 2.5, 10, 5],
          "circle-color": "#888888",
          "circle-stroke-color": ["case", ["==", ["get", "flagged"], 1], themeColor("--text", "#18181b"), themeColor("--surface", "#ffffff")],
          "circle-stroke-width": ["case", ["==", ["get", "flagged"], 1], 1.5, 0.5],
        },
      });
      m.addLayer({
        id: "selected",
        type: "circle",
        source: "stations",
        filter: ["==", ["get", "station_uid"], ""],
        paint: { "circle-radius": 9, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": themeColor("--accent", "#b45309"), "circle-stroke-width": 2 },
      });
      m.addSource("profile", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "profile-line", type: "line", source: "profile", paint: { "line-color": themeColor("--accent", "#b45309"), "line-width": 2, "line-dasharray": [3, 2] } });
      m.addLayer({ id: "profile-pts", type: "circle", source: "profile", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 4, "circle-color": themeColor("--accent", "#b45309") } });
      setReady(true);
    });
    m.on("click", (e) => {
      const p = latest.current;
      if (p.drawing) {
        p.onAddVertex([Number(e.lngLat.lng.toFixed(5)), Number(e.lngLat.lat.toFixed(5))]);
        return;
      }
      const hit = m.queryRenderedFeatures(e.point, { layers: ["stations"] })[0];
      p.onSelect(hit ? String(hit.properties?.station_uid ?? "") : null);
    });
    m.on("mouseenter", "stations", () => (m.getCanvas().style.cursor = "pointer"));
    m.on("mouseleave", "stations", () => (m.getCanvas().style.cursor = latest.current.drawing ? "crosshair" : ""));
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
    // The map is created once; props are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Theme: repaint basemap and chrome colours.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setPaintProperty("bg", "background-color", themeColor("--surface-2", "#f4f4f5"));
    m.setPaintProperty("land", "fill-color", themeColor("--surface", "#ffffff"));
    m.setPaintProperty("borders", "line-color", themeColor("--line", "#e4e4e7"));
    m.setPaintProperty("contours", "line-color", themeColor("--text-2", "#52525b"));
  }, [props.themeKey, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("stations") as GeoJSONSource).setData((props.stations as unknown as GeoJSON.FeatureCollection) ?? EMPTY);
  }, [props.stations, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setPaintProperty("stations", "circle-color", stationColor(props) as maplibregl.ExpressionSpecification);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.colorProperty, props.limits[0], props.limits[1], props.cmap, props.categorical, props.themeKey, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setFilter("selected", ["==", ["get", "station_uid"], props.selected ?? ""]);
  }, [props.selected, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const g = props.gridImage;
    if (g) (m.getSource("grid") as ImageSource).updateImage({ url: g.url, coordinates: corners(g.bounds) });
    m.setPaintProperty("grid", "raster-opacity", g && props.showGrid ? props.opacity : 0);
    const h = props.hatchImage;
    if (h) (m.getSource("hatch") as ImageSource).updateImage({ url: h.url, coordinates: corners(h.bounds) });
    m.setPaintProperty("hatch", "raster-opacity", h && props.showGrid ? 1 : 0);
  }, [props.gridImage, props.hatchImage, props.showGrid, props.opacity, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("contours") as GeoJSONSource).setData(props.contours ?? EMPTY);
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    // Labels as DOM markers (no glyph server needed): one per contour line, at its midpoint.
    // Only the longest line per level is labelled (max 24 labels) to keep the map readable.
    const longest = new Map<string, GeoJSON.Feature>();
    for (const f of props.contours?.features ?? []) {
      if (f.geometry.type !== "LineString") continue;
      const n = (f.geometry as GeoJSON.LineString).coordinates.length;
      const key = String(f.properties?.level);
      const cur = longest.get(key);
      if (n > 25 && (!cur || n > (cur.geometry as GeoJSON.LineString).coordinates.length)) longest.set(key, f);
    }
    for (const f of [...longest.values()].slice(0, 24)) {
      const c = (f.geometry as GeoJSON.LineString).coordinates;
      const mid = c[Math.floor(c.length / 2)] as [number, number];
      const div = document.createElement("div");
      div.className = "contour-label";
      div.textContent = String(f.properties?.level ?? "");
      markers.current.push(new maplibregl.Marker({ element: div }).setLngLat(mid).addTo(m));
    }
  }, [props.contours, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const pts = props.profileLine;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        ...(pts.length >= 2 ? [{ type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: pts } }] : []),
        ...pts.map((p) => ({ type: "Feature" as const, properties: {}, geometry: { type: "Point" as const, coordinates: p } })),
      ],
    };
    (m.getSource("profile") as GeoJSONSource).setData(fc);
    m.getCanvas().style.cursor = props.drawing ? "crosshair" : "";
  }, [props.profileLine, props.drawing, ready]);

  useEffect(() => {
    const m = map.current;
    if (m && props.extent) m.fitBounds(props.extent, { padding: 40, duration: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.extent?.join(",")]);

  // maplibre-gl.css (unlayered) sets `.maplibregl-map { position: relative }`, which beats layered
  // Tailwind utilities, so the absolute box is a wrapper and the map fills it.
  return (
    <div className="absolute inset-0">
      <div ref={el} className="h-full w-full" role="application" aria-label="Map of stations and gridded anomalies" />
    </div>
  );
}

const transparentPixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
