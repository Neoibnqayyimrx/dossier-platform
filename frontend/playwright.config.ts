import { defineConfig } from "@playwright/test";

/**
 * The happy-path end-to-end test (P11c).
 *
 * WHY this does NOT start the backend for you: the API needs Postgres, a
 * seeded knowledge base, and LLM/embedding providers configured — state a
 * test runner shouldn't be inventing. The spec skips itself with a clear
 * message when the API isn't reachable, so `npm run e2e` is safe to run
 * anywhere; see frontend/README.md for the three commands that bring the
 * stack up.
 */
export default defineConfig({
  testDir: "./e2e",
  // Serial: the spec creates real rows through the real API, and a
  // parallel second worker would race it for the same seeded project.
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run start",
    url: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
