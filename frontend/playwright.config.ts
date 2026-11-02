import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  // The specs are full-stack E2E: they drive the Next.js app against the real
  // backend API (default http://localhost:8999/api/v1). The backend must run
  // in dev/test transport mode so console-email payloads surface.
  webServer: [
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
    {
      command: "python -m uvicorn app.main:app --port 8999",
      cwd: "../backend",
      url: "http://localhost:8999/health",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: {
        ...process.env,
        // Specs cover worker-driven outcomes (notification delivery, dependency
        // unblocking, indexing), so the scheduler must run: APP_ENV=test skips it.
        APP_ENV: "development",
        VCOS_TEST_MODE: "1",
        EMAIL_TRANSPORT: "console",
      } as Record<string, string>,
    },
  ],
});
