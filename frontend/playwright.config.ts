import { defineConfig, devices } from "@playwright/test";

// This test creates real accounts. The runner/CI owns a fresh local Compose project.
if (process.env.ALLOW_DISPOSABLE_E2E !== "1" || !/^ss-r5-e2e-[a-z0-9-]+$/.test(process.env.E2E_COMPOSE_PROJECT ?? "")) {
  throw new Error("Use python scripts/run_auth_e2e.py with a fresh disposable Compose environment.");
}

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/verify-environment.ts",
  timeout: 60000,
  expect: { timeout: 10000 },
  globalTimeout: 180000,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000", trace: "off", screenshot: "off", ...devices["Desktop Chrome"],
    // Optional local fallback when the managed-browser download is unavailable.
    channel: process.env.PLAYWRIGHT_CHANNEL === "chrome" ? "chrome" : undefined,
  },
  projects: [{ name: "chromium" }],
});
