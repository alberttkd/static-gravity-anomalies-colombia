import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

URL.createObjectURL = vi.fn(() => "blob:mock");

// MapLibre needs WebGL; a recording fake is enough for component tests.
vi.mock("maplibre-gl", () => {
  class FakeSource {
    data: unknown = null;
    setData(d: unknown) {
      this.data = d;
    }
    updateImage(o: unknown) {
      this.data = o;
    }
  }
  class FakeMap {
    static last: FakeMap | null = null;
    handlers: Record<string, ((e: unknown) => void)[]> = {};
    sources: Record<string, FakeSource> = {};
    paint: Record<string, unknown> = {};
    filters: Record<string, unknown> = {};
    canvas = { style: { cursor: "" } };
    constructor() {
      FakeMap.last = this;
      setTimeout(() => this.fire("load", {}), 0);
    }
    on(ev: string, a: unknown, b?: unknown) {
      const fn = (typeof a === "function" ? a : b) as (e: unknown) => void;
      (this.handlers[ev] ??= []).push(fn);
      return this;
    }
    fire(ev: string, e: unknown) {
      (this.handlers[ev] ?? []).forEach((f) => f(e));
    }
    addControl() {
      return this;
    }
    addSource(id: string) {
      this.sources[id] = new FakeSource();
    }
    addLayer() {}
    getSource(id: string) {
      return this.sources[id];
    }
    setPaintProperty(layer: string, prop: string, v: unknown) {
      this.paint[`${layer}.${prop}`] = v;
    }
    setFilter(layer: string, f: unknown) {
      this.filters[layer] = f;
    }
    queryRenderedFeatures() {
      return [{ properties: { station_uid: "SYN:A" } }];
    }
    getCanvas() {
      return this.canvas;
    }
    fitBounds() {}
    remove() {}
  }
  class Marker {
    setLngLat() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {}
  }
  class Ctrl {}
  const mod = { Map: FakeMap, Marker, NavigationControl: Ctrl, ScaleControl: Ctrl, AttributionControl: Ctrl };
  return { default: mod, ...mod };
});

vi.mock("plotly.js-basic-dist-min", () => ({ default: { react: vi.fn(() => Promise.resolve()), purge: vi.fn() } }));
