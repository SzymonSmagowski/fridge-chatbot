/**
 * E2E: first-time device pairing flow (Architect §4.1 + §5.1).
 *
 * The flow is single-screen and redirect-based. The kiosk hits
 * `POST /pairing/start`, receives an `authorize_url`, and navigates the
 * browser to it. Google then redirects to `GET /oauth/google/callback`
 * which 302s back with `?token=<device-jwt>` — the frontend persists the
 * token and lands on the home shell.
 */
import { test, expect } from "@playwright/test";
import { API, JWT, mockBackend, stubWebSocket } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await stubWebSocket(page);
});

test.describe("Pairing", () => {
  test("[e2e] root with no token redirects to /pair", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/pair$/);
    await expect(
      page.getByRole("heading", { name: /set up your fridge/i }),
    ).toBeVisible();
  });

  test("[e2e] pair screen shows the start CTA and the legacy escape link", async ({ page }) => {
    await page.goto("/pair");
    await expect(
      page.getByRole("button", { name: /start pairing/i }),
    ).toBeEnabled();
    await expect(
      page.getByRole("link", { name: /legacy login/i }),
    ).toHaveAttribute("href", "/login");
  });

  test("[e2e] start button POSTs /pairing/start and redirects to authorize_url", async ({ page }) => {
    const fakeAuthUrl =
      "http://localhost:3000/__stubbed_google__"; // same-origin so navigation actually completes
    await page.route(`${API}/pairing/start`, async (route) => {
      const body = route.request().postDataJSON() as { device_label?: string };
      expect(body.device_label).toBe("Kitchen Fridge");
      await route.fulfill({
        json: { pairing_id: "abc123", authorize_url: fakeAuthUrl },
      });
    });
    // Stub the navigation target so the redirect lands on a 200 page.
    await page.route(fakeAuthUrl, (route) =>
      route.fulfill({ contentType: "text/html", body: "<h1>fake google</h1>" }),
    );

    await page.goto("/pair");
    await page.getByRole("button", { name: /start pairing/i }).click();

    await expect(page).toHaveURL(/__stubbed_google__/);
  });

  test("[e2e] /pair/complete?token=… persists the device JWT and lands on home", async ({ page }) => {
    await mockBackend(page);
    await page.goto(`/pair/complete?token=${encodeURIComponent(JWT)}`);
    // After the token is consumed we replace() to /, which renders the kiosk shell.
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("tab", { name: /notes/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const stored = await page.evaluate(() =>
      window.localStorage.getItem("fridge-chatbot-token"),
    );
    expect(stored).toBe(JWT);
  });

  test("[e2e] / catches the OAuth callback `?token=` redirect target too", async ({ page }) => {
    // Backend currently 302s to /settings?paired=1&token=… or /?token=… —
    // the root must accept the param so future backend tweaks don't break.
    await mockBackend(page);
    await page.goto(`/?token=${encodeURIComponent(JWT)}`);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("tab", { name: /notes/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("[e2e] /pair/complete with no token shows the missing-token recovery screen", async ({ page }) => {
    await page.goto("/pair/complete");
    await expect(
      page.getByRole("heading", { name: /didn't get a token/i }),
    ).toBeVisible();
    await page.getByRole("button", { name: /try again/i }).click();
    await expect(page).toHaveURL(/\/pair$/);
  });
});
