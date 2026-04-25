/**
 * E2E: App shell — tab navigation, status bar, initial route.
 */
import { test, expect } from "@playwright/test";
import { mockBackend, seedToken, stubWebSocket } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await seedToken(page);
  await stubWebSocket(page);
  await mockBackend(page);
});

test.describe("App shell", () => {
  test("[e2e] AppShell: unauthenticated user gets redirected to /pair", async ({ page }) => {
    // Clear token first — seedToken added it, so we undo for this test only.
    await page.addInitScript(() => {
      window.localStorage.removeItem("fridge-chatbot-token");
    });
    await page.goto("/");
    await expect(page).toHaveURL(/\/pair/);
  });

  test("[e2e] AppShell: authenticated user lands on Notes by default", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("tab", { name: /notes/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("[e2e] AppShell: all four tabs are navigable and aria-selected flips", async ({ page }) => {
    await page.goto("/");
    for (const name of ["Chat", "Notes", "Calendar", "Settings"]) {
      await page.getByRole("tab", { name: new RegExp(name, "i") }).click();
      await expect(
        page.getByRole("tab", { name: new RegExp(name, "i") }),
      ).toHaveAttribute("aria-selected", "true");
    }
  });

  test("[e2e] AppShell: status bar shows the family name (stubbed)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/the magowski family/i)).toBeVisible();
  });

  test("[e2e] AppShell: tab nav is exposed as role=tablist with label", async ({ page }) => {
    await page.goto("/");
    const list = page.getByRole("tablist", { name: /primary navigation/i });
    await expect(list).toBeVisible();
  });
});
