import { test } from "@playwright/test";
import { mockBackend, seedToken, stubWebSocket } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await seedToken(page);
  await stubWebSocket(page);
  await mockBackend(page);
});

test("screenshot: notes tab home state", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=Shopping list");
  await page.waitForTimeout(800);
  await page.screenshot({ path: "tests/e2e/screenshots/notes-home.png", fullPage: false });
});

test("screenshot: settings tab", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /settings/i }).click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: "tests/e2e/screenshots/settings.png", fullPage: false });
});

test("screenshot: calendar tab empty week", async ({ page }) => {
  await mockBackend(page, { notes: [] });
  await page.goto("/");
  await page.getByRole("tab", { name: /calendar/i }).click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: "tests/e2e/screenshots/calendar-empty.png", fullPage: false });
});

test("screenshot: event editor sheet", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /calendar/i }).click();
  await page.getByRole("button", { name: /new event/i }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "tests/e2e/screenshots/event-editor.png", fullPage: false });
});

test("screenshot: confirm delete dialog", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /settings/i }).click();
  await page.getByRole("button", { name: /more actions for family volvo/i }).click();
  await page.getByRole("menuitem", { name: /delete permanently/i }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "tests/e2e/screenshots/confirm-delete.png", fullPage: false });
});
