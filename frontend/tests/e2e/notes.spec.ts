/**
 * E2E: Notes tab user journeys from the UI design doc + notes.md spec.
 * All tests run against the Next.js dev server with a stubbed backend — no
 * real backend process required.
 */
import { test, expect } from "@playwright/test";
import { mockBackend, seedToken, stubWebSocket, NOTES } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await seedToken(page);
  await stubWebSocket(page);
  await mockBackend(page);
});

test.describe("Notes tab", () => {
  test("[e2e] Notes: populated board renders Shopping list, Dentist appt, and Family-wide rows", async ({ page }) => {
    await page.goto("/");
    // Default landing tab is Notes.
    await expect(page.getByRole("tab", { name: /notes/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByText("Shopping list")).toBeVisible();
    await expect(page.getByText("Dentist appt for Ola")).toBeVisible();
    await expect(page.getByText("Family-wide")).toBeVisible();
  });

  test("[e2e] Notes: adding a note via the quick input appends it to the board", async ({ page }) => {
    let posted: { content: string; assignee_member_id: string | null } | null = null;
    await mockBackend(page, {
      onCreateNote: (b) => {
        posted = b as { content: string; assignee_member_id: string | null };
      },
    });
    await page.goto("/");
    await page.getByLabel(/quick-add a note/i).fill("Buy oat milk");
    await page.getByRole("button", { name: /^add$/i }).click();
    await expect.poll(() => posted?.content).toBe("Buy oat milk");
    await expect(page.getByText("Buy oat milk")).toBeVisible();
  });

  test("[e2e] Notes: shopping-list checkbox toggles from pending → done", async ({ page }) => {
    await page.goto("/");
    const milk = page.getByRole("checkbox", { name: "milk" });
    await expect(milk).toHaveAttribute("aria-checked", "false");
    await milk.click();
    // Optimistic update — UI flips before the PATCH returns.
    await expect(milk).toHaveAttribute("aria-checked", "true");
  });

  test("[e2e] Notes: empty state shows 'This board is empty' CTA", async ({ page }) => {
    await mockBackend(page, { notes: [] });
    await page.goto("/");
    await expect(page.getByText(/this board is empty/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /new note/i })).toBeVisible();
  });

  test("[e2e] Notes: assignee picker is a radiogroup with keyboard-accessible options", async ({ page }) => {
    await page.goto("/");
    const group = page.getByRole("radiogroup", { name: /assign to a family member/i });
    await expect(group).toBeVisible();
    const options = group.getByRole("radio");
    expect(await options.count()).toBeGreaterThan(1);
    // Exactly one is checked at boot (family-wide is the default).
    const checked = await options.evaluateAll((nodes) =>
      nodes.filter((n) => n.getAttribute("aria-checked") === "true").length,
    );
    expect(checked).toBe(1);
  });

  test("[e2e] Notes: page has no unexpected console errors after basic flow", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/");
    await page.getByLabel(/quick-add a note/i).fill("Test");
    await page.getByRole("button", { name: /^add$/i }).click();
    await page.waitForTimeout(500);
    // Filter out MSW or family-events noise that is environmental, not a UX bug.
    const real = errors.filter(
      (e) =>
        !/websocket/i.test(e) &&
        !/\[MSW\]/i.test(e) &&
        !/family-events/i.test(e),
    );
    expect(real).toEqual([]);
  });
});
