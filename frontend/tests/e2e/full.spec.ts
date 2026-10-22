import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8000/api/v1";
const PUBLIC_API = "http://127.0.0.1:8001/api/v1";
const py = resolve(process.cwd(), "..", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

type Station = { properties: Record<string, unknown> & { station_uid: string } };
const stationsInUi = (page: Page) =>
  page.evaluate(() => (window as unknown as { __gravanom: { stations?: { features: Station[] } } }).__gravanom.stations?.features ?? []);

async function waitRun(page: Page, n = 1900) {
  await page.waitForFunction((min) => {
    const g = (window as unknown as { __gravanom?: { stations?: { features: unknown[] } } }).__gravanom;
    return (g?.stations?.features.length ?? 0) > min;
  }, n);
}

test("AT-02 density change: the Δ CBA layer matches the API at three stations", async ({ page, request }) => {
  await page.goto("/");
  await waitRun(page);
  await page.getByRole("tab", { name: "Density" }).click();
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.getByText(/Mean Δ CBA/)).toBeVisible();
  await expect(page.getByRole("radio", { name: "Δ CBA (density)" })).toHaveAttribute("aria-checked", "true");
  const api = await (await request.post(`${API}/sensitivity/density`, { data: { dataset: "synthetic", densities: [2670, 2300] } })).json();
  const apiMap = new Map<string, number>(api.stations.features.map((f: Station) => [f.properties.station_uid, f.properties.delta_cba_mgal as number]));
  const ui = (await stationsInUi(page)).filter((f) => typeof f.properties.delta_cba_mgal === "number");
  for (const f of [ui[0], ui[Math.floor(ui.length / 2)], ui[ui.length - 1]]) {
    expect(Math.abs((f?.properties.delta_cba_mgal as number) - (apiMap.get(f?.properties.station_uid as string) as number))).toBeLessThan(1e-6);
  }
});

test("AT-03 gridding with auto: grid, σ, transparent unsupported cells and CV panel", async ({ page, request }) => {
  await page.goto("/");
  await waitRun(page);
  await page.getByRole("button", { name: "Run gridding" }).click();
  await expect(page.getByText("Grid layer")).toBeVisible({ timeout: 170_000 });
  await page.getByRole("tab", { name: "Validation" }).click();
  await expect(page.getByText("Block-CV RMSE")).toBeVisible();
  await expect(page.getByText("sd(z)")).toBeVisible();
  await expect(page.getByText("95 % coverage")).toBeVisible();
  await page.getByRole("radio", { name: "σ cal." }).click();
  const gridId = await page.evaluate(() => (window as unknown as { __gravanom: { gridId: string } }).__gravanom.gridId);
  const png = await request.get(`${API}/grids/${gridId}/image?layer=value`);
  expect(png.headers()["content-type"]).toBe("image/png");
  const meta = await (await request.get(`${API}/grids/${gridId}`)).json();
  expect(meta.supported_share).toBeLessThan(1);
});

test("AT-04 profile: chart with ±2σ band, stations within 2 km and H", async ({ page }) => {
  await page.goto("/");
  await waitRun(page);
  await page.getByRole("button", { name: "Run gridding" }).click();
  await expect(page.getByText("Grid layer")).toBeVisible({ timeout: 170_000 });
  await page.getByRole("tab", { name: "Profile" }).click();
  await page.getByLabel(/Or type vertices/).fill("-75.4,9.0; -74.6,9.0");
  await page.getByRole("button", { name: "Go" }).click();
  const chart = page.getByTestId("profile-chart");
  await expect(chart).toBeVisible();
  await expect(chart.getByRole("img", { name: /±2σ band and \d+ stations within the buffer/ })).toBeVisible();
  await expect(chart.locator(".legendtext", { hasText: "H" })).toBeVisible();
});

test("AT-05 legacy mode reproduces the spreadsheets (private, local only)", async ({ page }) => {
  test.skip(!process.env.GRAVANOM_PRIVATE_DATA_DIR, "needs GRAVANOM_PRIVATE_DATA_DIR (local only)");
  await page.goto("/");
  await page.getByLabel("Dataset").selectOption("private");
  await page.getByLabel("Legacy mode (legacy spreadsheets)").click();
  await page.getByRole("button", { name: "Run reduction" }).click();
  await page.waitForFunction(() => {
    const g = (window as unknown as { __gravanom?: { runId?: string; stations?: { features: Station[] } } }).__gravanom;
    return !!g?.stations?.features.some((f) => String(f.properties.station_uid).startsWith("A:"));
  });
  const ui = await stationsInUi(page);
  const picks = ui.filter((f) => /^(A|B):\d+$/.test(f.properties.station_uid)).filter((_, i, a) => i === 0 || i === Math.floor(a.length / 2) || i === a.length - 1);
  const ids = picks.map((f) => f.properties.station_uid);
  // Read the cached spreadsheet values for the three stations (never written to disk or logs).
  const out = execFileSync(py, [
    "-c",
    "import json,sys;from pathlib import Path;from gravanom.io.legacy import read_sources;" +
      "r=Path(sys.argv[1]);t=read_sources(r);" +
      "res={};[res.__setitem__(u,dict(zip(['aaa','abs','abt'],t[u.split(':')[0]].legacy.set_index('source_id').loc[u.split(':')[1],['aaa','abs','abt']].tolist()))) for u in sys.argv[2:]];print(json.dumps(res))",
    process.env.GRAVANOM_PRIVATE_DATA_DIR as string,
    ...ids,
  ]).toString();
  const sheet = JSON.parse(out) as Record<string, { aaa: number; abs: number; abt: number }>;
  for (const f of picks) {
    const s = sheet[f.properties.station_uid] as { aaa: number; abs: number; abt: number };
    expect(Math.abs((f.properties.faa_mgal as number) - s.aaa)).toBeLessThan(1e-6);
    expect(Math.abs((f.properties.sba_mgal as number) - s.abs)).toBeLessThan(1e-6);
    expect(Math.abs((f.properties.cba_mgal as number) - s.abt)).toBeLessThan(1e-6);
  }
});

test("AT-06 COG export opens with rasterio (EPSG:9377, NaN nodata) and includes metadata.json", async ({ request }) => {
  const run = await (await request.post(`${API}/reductions`, { data: { dataset: "synthetic" } })).json();
  const job = await (await request.post(`${API}/gridding-jobs`, { data: { run_id: run.run_id, config: { method: "idw", cell_size_m: 1000 } } })).json();
  let st = job;
  for (let i = 0; i < 120 && st.status !== "done" && st.status !== "failed"; i++) {
    await new Promise((r) => setTimeout(r, 500));
    st = await (await request.get(`${API}/gridding-jobs/${job.job_id}`)).json();
  }
  expect(st.status).toBe("done");
  const zip = await request.get(`${API}/grids/${st.grid_id}/download?format=cog&layer=value`);
  const dir = mkdtempSync(join(tmpdir(), "gae-"));
  const file = join(dir, "grid.zip");
  writeFileSync(file, await zip.body());
  const out = execFileSync(py, [
    "-c",
    "import gravanom,sys,zipfile,io,rasterio,math;z=zipfile.ZipFile(sys.argv[1]);n=[x for x in z.namelist() if x.endswith('.tif')][0];" +
      "d=z.read(n);f=rasterio.io.MemoryFile(d).open();print(f.crs.to_epsg(), math.isnan(f.nodata), 'metadata.json' in z.namelist())",
    file,
  ]).toString().trim();
  expect(out).toBe("9377 True True");
});

test("AT-07 provenance panel (full mode) shows input hashes, versions, configuration and seed", async ({ page }) => {
  await page.goto("/");
  await waitRun(page);
  await page.getByRole("button", { name: "Provenance" }).click();
  const p = page.getByTestId("provenance");
  await expect(p).toContainText("synthetic_survey.csv");
  await expect(p).toContainText("gravanom");
  await expect(p).toContainText("Resolved configuration");
  await expect(p).toContainText("20261022");
});

test("AT-08 public mode: the private dataset is not listed and direct calls return 503", async ({ request }) => {
  const ds = await (await request.get(`${PUBLIC_API}/datasets`)).json();
  expect(ds.map((d: { id: string }) => d.id)).toEqual(["synthetic"]);
  const r = await request.get(`${PUBLIC_API}/datasets/private/qc`);
  expect(r.status()).toBe(503);
  expect((await r.json()).code).toBe("PRIVATE_DATA_UNAVAILABLE");
});
