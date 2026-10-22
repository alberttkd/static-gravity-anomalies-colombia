import { describe, expect, it } from "vitest";
import type { StationCollection } from "../../src/api/types";
import {
  CMAPS,
  cmapFor,
  colorAt,
  cssGradient,
  fmt,
  interpolateExpression,
  limitsFor,
  sequentialLimits,
  symmetricLimits,
  ticks,
} from "../../src/lib/colormaps";
import { deriveStations, histogram, parseCoordinates, qcCode, values } from "../../src/lib/derive";

describe("colormaps", () => {
  it("uses symmetric limits centred at 0 for anomalies", () => {
    const [lo, hi] = symmetricLimits([-3, -1, 0, 2, 10, Number.NaN, null]);
    expect(lo).toBe(-hi);
    expect(hi).toBeGreaterThan(0);
    expect(symmetricLimits([])).toEqual([-1, 1]);
    expect(limitsFor("cba_mgal", [1, 2, 3])[0]).toBeLessThan(0);
  });

  it("centres the diverging map at 0 (white)", () => {
    expect(colorAt(0, -5, 5, "RdBu_r")).toBe("rgb(247, 247, 247)");
    expect(colorAt(-99, -5, 5, "RdBu_r")).toBe("rgb(5, 48, 97)");
    expect(colorAt(99, -5, 5, "RdBu_r")).toBe("rgb(103, 0, 31)");
  });

  it("uses only colour-blind-safe palettes", () => {
    expect(Object.keys(CMAPS).sort()).toEqual(["RdBu_r", "viridis"]);
    expect(cmapFor("height_m")).toBe("viridis");
    expect(cmapFor("sigma_cba_mgal")).toBe("viridis");
    expect(cmapFor("delta_cba_mgal")).toBe("RdBu_r");
  });

  it("builds sequential limits, expressions, gradients and ticks", () => {
    expect(sequentialLimits([5, 5])).toEqual([5, 6]);
    expect(sequentialLimits([])).toEqual([0, 1]);
    const e = interpolateExpression("cba_mgal", -2, 2, "RdBu_r");
    expect(e.slice(0, 2)).toEqual(["interpolate", ["linear"]]);
    expect(e[3]).toBe(-2);
    expect(e[e.length - 2]).toBe(2);
    expect(cssGradient("viridis")).toContain("#440154");
    expect(ticks(-10, 10)).toEqual([-10, -5, 0, 5, 10]);
    expect(fmt(-1.234, 2)).toBe("−1.23");
    expect(fmt(null)).toBe("n/a");
  });
});

const fc: StationCollection = {
  type: "FeatureCollection",
  properties: { label: "SYNTHETIC" },
  features: [
    { type: "Feature", geometry: { type: "Point", coordinates: [-75, 9] }, properties: { station_uid: "A", qc_flags: [], cba_mgal: -10 } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-75, 9.1] }, properties: { station_uid: "B", qc_flags: ["ERROR_RANGE"], cba_mgal: 9999 } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-75, 9.2] }, properties: { station_uid: "C", qc_flags: ["TC_SUSPECT"], cba_mgal: null } },
  ],
};

describe("derive", () => {
  it("adds deltas and QC codes, nulls error-flagged stations", () => {
    const ref: StationCollection = { ...fc, features: fc.features.map((f) => ({ ...f, properties: { ...f.properties, cba_mgal: -9 } })) };
    const d = deriveStations(fc, ref, new Map([["A", -1.1]]));
    const a = d?.features[0]?.properties;
    expect(a?.delta_ref_mgal).toBe(-1);
    expect(a?.delta_cba_mgal).toBe(-1.1);
    expect(d?.features[1]?.properties.cba_mgal).toBeNull();
    expect(d?.features[1]?.properties.qc).toBe(4);
    expect(d?.features[2]?.properties.flagged).toBe(1);
    expect(values(d, "cba_mgal")).toEqual([-10]);
    expect(deriveStations(undefined, undefined)).toBeUndefined();
  });

  it("codes QC categories", () => {
    expect(qcCode([])).toBe(0);
    expect(qcCode(["H_NONPOSITIVE"])).toBe(1);
    expect(qcCode(["TC_SUSPECT"])).toBe(2);
    expect(qcCode(["DUPLICATE_POSITION"])).toBe(3);
    expect(qcCode(["CONFLICT_SHARED_ID"])).toBe(4);
  });

  it("bins histograms and parses typed coordinates", () => {
    const h = histogram([-1, 0, 0.5, 1, 5], 2, -1, 1);
    expect(h.counts).toEqual([1, 3]);
    expect(parseCoordinates("-75.3,9.0; -74.7, 9.0")).toEqual([
      [-75.3, 9],
      [-74.7, 9],
    ]);
    expect(parseCoordinates("-75,9")).toBeNull();
    expect(parseCoordinates("a,b; c,d")).toBeNull();
    expect(parseCoordinates("-200,9; 0,0")).toBeNull();
  });
});
