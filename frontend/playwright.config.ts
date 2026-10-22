import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end acceptance tests AT-01..AT-08 (MASTER_GUIDE §8 P9).
 * - static:  the public demo (synthetic, no backend) built with `npm run build:static`.
 * - full:    the UI against the API (synthetic; private dataset if GRAVANOM_PRIVATE_DATA_DIR is set).
 * - public:  a second API instance with GRAVANOM_PUBLIC_MODE=true (AT-08).
 */
const py = `"${resolve(process.cwd(), "..", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python")}"`;
const backend = `"${resolve(process.cwd(), "..", "backend")}"`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, trace: "retain-on-failure" },
  webServer: [
    { command: "npx vite preview --mode static --outDir dist-static --host 127.0.0.1 --port 4173 --strictPort", port: 4173, reuseExistingServer: true },
    {
      command: `${py} -m uvicorn app.main:app --app-dir ${backend} --port 8000`,
      port: 8000,
      reuseExistingServer: true,
      timeout: 120_000,
      env: { GRAVANOM_PUBLIC_MODE: "false", GRAVANOM_PRIVATE_DATA_DIR: process.env.GRAVANOM_PRIVATE_DATA_DIR ?? "", PYTHONWARNINGS: "ignore" },
    },
    { command: "npx vite preview --host 127.0.0.1 --port 4174 --strictPort", port: 4174, reuseExistingServer: true },
    {
      command: `${py} -m uvicorn app.main:app --app-dir ${backend} --port 8001`,
      port: 8001,
      reuseExistingServer: true,
      timeout: 120_000,
      env: { GRAVANOM_PUBLIC_MODE: "true", GRAVANOM_PRIVATE_DATA_DIR: "", PYTHONWARNINGS: "ignore" },
    },
  ],
  projects: [
    { name: "static", testMatch: /static\.spec\.ts/, use: { baseURL: "http://127.0.0.1:4173" } },
    { name: "full", testMatch: /full\.spec\.ts/, use: { baseURL: "http://127.0.0.1:4174" } },
  ],
});
