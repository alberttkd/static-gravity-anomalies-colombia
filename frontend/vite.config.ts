/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `--mode static` builds the public demo that reads precomputed artifacts from /demo
// (synthetic data only). The default mode talks to the FastAPI backend.
export default defineConfig(({ mode }) => ({
  base: mode === "static" ? "./" : "/",
  plugins: [react(), tailwindcss()],
  define: { "import.meta.env.VITE_STATIC_MODE": JSON.stringify(mode === "static" ? "1" : process.env.VITE_STATIC_MODE ?? "0") },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { proxy: { "/api": process.env.API_TARGET ?? "http://127.0.0.1:8000" } },
  build: { chunkSizeWarningLimit: 1500, outDir: mode === "static" ? "dist-static" : "dist" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/unit/setup.ts"],
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    css: false,
    coverage: { provider: "v8", include: ["src/**/*.{ts,tsx}"], exclude: ["src/api/schema.d.ts", "src/main.tsx", "src/vite-env.d.ts"], reporter: ["text-summary", "text"] },
  },
}));
