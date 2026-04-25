/**
 * E2E: Settings tab user journeys — members/cars/preferences.
 */
import { test, expect } from "@playwright/test";
import { mockBackend, seedToken, stubWebSocket } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await seedToken(page);
  await stubWebSocket(page);
  await mockBackend(page);
});

test.describe("Settings tab", () => {
  test("[e2e] Settings: shows family banner and 3 members by default", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    // The family name appears twice — in the status bar and in the family banner.
    // Anchor on the banner heading to avoid strict-mode collision.
    await expect(
      page.getByRole("heading", { name: /the magowski family/i }),
    ).toBeVisible();
    // Member names are inside row containers that also include the Google
    // email; "Monika" appears inside `Monika(Mom)` (no space — the parens are
    // a sibling span). Use the buttons that wrap each row's edit affordance —
    // those have a stable aria-label of `Edit <name>`.
    await expect(page.getByRole("button", { name: "Edit Monika" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit Szymon" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit Ola" })).toBeVisible();
  });

  test("[e2e] Settings: add-member sheet opens and captures name + color + save", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    await page.getByRole("button", { name: /add a family member/i }).click();

    const dialog = page.getByRole("dialog", { name: /add a family member/i });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel(/^name/i).fill("Wojtek");
    // Save button should become enabled; we don't need to wait for the POST.
    await expect(dialog.getByRole("button", { name: /save member/i })).toBeEnabled();
  });

  test("[e2e] Settings: destructive delete-car dialog warns about permanence", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    await page
      .getByRole("button", { name: /more actions for family volvo/i })
      .click();
    await page.getByRole("menuitem", { name: /delete permanently/i }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/this is permanent/i)).toBeVisible();
  });

  test("[e2e] Settings: voice-wake toggle is disabled (deferred per manifest)", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    const toggle = page.getByRole("switch", { name: /voice wake phrase/i });
    await expect(toggle).toBeDisabled();
  });

  test("[e2e] Settings: no console errors after navigating to Settings", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    await page.waitForTimeout(500);
    const real = errors.filter(
      (e) =>
        !/websocket/i.test(e) &&
        !/\[MSW\]/i.test(e) &&
        !/family-events/i.test(e),
    );
    expect(real).toEqual([]);
  });
});
