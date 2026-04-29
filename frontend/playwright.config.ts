import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for fridge-chatbot frontend.
 *
 * The dev server and backend API are both stubbed from inside each spec via
 * `page.route(...)` so E2E tests run hermetically. They execute against the
 * Next.js dev server on port 3000 — the `webServer` block boots it.
 *
 * A11y assertions are done via `page.accessibility.snapshot()` / role-based
 * selectors — more stable than CSS selectors for our long-running kiosk UI.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000/pair",
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
