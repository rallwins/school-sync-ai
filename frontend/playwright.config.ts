import { defineConfig } from "@playwright/test";

// Expects backend on :8000 and the frontend on :3000 (see README "Run locally").
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000" },
});
