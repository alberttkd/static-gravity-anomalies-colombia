import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("AT-01 static demo shows synthetic stations, badge and mGal legend", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("dataset-badge")).toHaveText("SYNTHETIC DATA");
  await expect(page.getByText("(mGal)").first()).toBeVisible();
  await expect(page.getByText(/EPSG:9377/)).toBeVisible();
  await page.waitForFunction(() => {
    const g = (window as unknown as { __gravanom?: { stations?: { features: unknown[] } } }).__gravanom;
    return (g?.stations?.features.length ?? 0) > 1900;
  });
  await expect(page.getByText("Grid layer")).toBeVisible();
});

test("AT-07 (static) provenance panel shows hashes, versions and seed", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Provenance" }).click();
  const p = page.getByTestId("provenance");
  await expect(p).toContainText("synthetic_survey.csv");
  await expect(p).toContainText("harmonica");
  await expect(p).toContainText("20261022");
});

test("static demo validation view renders method comparison", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Validation" }).click();
  await expect(page.getByText(/Selected \/ IDW RMSE/)).toBeVisible();
  await expect(page.getByRole("cell", { name: /RK Matérn/ })).toBeVisible();
});

for (const theme of ["light", "dark"] as const) {
  test(`accessibility: no serious or critical axe violations (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/");
    await expect(page.getByTestId("dataset-badge")).toBeVisible();
    await page.getByRole("tab", { name: "Validation" }).click();
    await expect(page.getByText(/Selected \/ IDW RMSE/)).toBeVisible();
    const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
    const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(bad.map((v) => `${v.id}: ${v.nodes.length} nodes`)).toEqual([]);
  });
}
