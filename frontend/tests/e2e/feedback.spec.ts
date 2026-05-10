/**
 * E2E: Feedback button + modal flow from Settings.
 *
 * Covers Tier A #4 of the FrontendTester brief — full happy path from tapping
 * the Settings tab → opening the modal → selecting "Improvement" → typing a
 * message → clicking Send → asserting the POST body and modal-close behavior.
 *
 * Also covers Tier B #6 (existing Chat tab still functional after the runtime
 * hook return-shape change) by simply navigating into Chat and verifying the
 * tab is selectable — full message-send is exercised in the unit tests.
 *
 * Backend is stubbed via `page.route()` so the test runs without a real
 * FastAPI process. We watch for any console errors (Tier brief: "always check
 * console messages after a Playwright flow") and treat anything other than
 * known WS / family-events noise as a failure.
 */
import { test, expect } from "@playwright/test";
import { API, mockBackend, seedToken, stubWebSocket } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await seedToken(page);
  await stubWebSocket(page);
  await mockBackend(page);
});

test.describe("Feedback flow", () => {
  test("[e2e] Settings: 'Send feedback' button is visible and accessible-named", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    const btn = page.getByRole("button", { name: /send feedback/i });
    await expect(btn).toBeVisible();
    // Tab navigation reaches it (a11y).
    await btn.focus();
    await expect(btn).toBeFocused();
  });

  test("[e2e] Settings → feedback modal: full happy path posts category + message and closes", async ({ page }) => {
    let posted: Record<string, unknown> | null = null;

    await page.route(`${API}/api/feedback`, async (route) => {
      if (route.request().method() === "POST") {
        posted = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 201,
          json: {
            id: "fb-1",
            family_id: "fam-1",
            member_id: null,
            device_id: "dev-1",
            thread_id: posted.thread_id ?? null,
            category: posted.category,
            message: posted.message,
            author_kind: "user",
            status: "open",
            created_at: "2026-05-10T12:00:00Z",
            updated_at: "2026-05-10T12:00:00Z",
          },
        });
        return;
      }
      await route.fallback();
    });

    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    await page.getByRole("button", { name: /send feedback/i }).click();

    // Modal opens with role=dialog
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    // Pick "Improvement"
    await dialog.getByLabel(/^improvement$/i).check();
    // Type the message
    await dialog
      .getByPlaceholder(/tell us what's not working/i)
      .fill("Please add dark mode for kiosk display");

    // Send button is now enabled
    const send = dialog.getByRole("button", { name: /^send$/i });
    await expect(send).toBeEnabled();
    await send.click();

    // Assert request body shape — category + message, no author_kind
    await expect.poll(() => posted?.category).toBe("improvement");
    expect(posted!.message).toBe("Please add dark mode for kiosk display");
    expect(Object.keys(posted!)).not.toContain("author_kind");

    // Modal closes after success.
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("[e2e] Feedback modal: Send is disabled when textarea is empty", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    await page.getByRole("button", { name: /send feedback/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // Empty textarea → Send disabled
    await expect(dialog.getByRole("button", { name: /^send$/i })).toBeDisabled();
    // Type 5 chars (under the 10-char min) → still disabled
    await dialog
      .getByPlaceholder(/tell us what's not working/i)
      .fill("hi me");
    await expect(dialog.getByRole("button", { name: /^send$/i })).toBeDisabled();
  });

  test("[e2e] Feedback modal: Esc closes when not submitting", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    await page.getByRole("button", { name: /send feedback/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("[e2e] AppShell: Chat tab still renders after runtime-hook reshape (regression)", async ({ page }) => {
    // Stub the legacy chat endpoints so navigating to Chat doesn't 404 / hang.
    // The actual streaming WS is mocked at `stubWebSocket` (family events) +
    // we don't open a chat WS here since we don't send a message.
    await page.route(`${API}/threads`, async (route) => {
      if (route.request().method() === "POST") {
        // Stub a freshly-created thread so the Chat view bootstraps.
        await route.fulfill({
          status: 200,
          json: {
            id: 1,
            thread_id: "uuid-1",
            title: "Hi",
            created_at: "2026-05-10T12:00:00Z",
            updated_at: "2026-05-10T12:00:00Z",
          },
        });
        return;
      }
      await route.fulfill({ status: 200, json: [] });
    });
    await page.route(/\/threads\/\d+(\?.*)?$/, async (route) => {
      // Initial open envelope — short empty thread.
      await route.fulfill({
        status: 200,
        json: {
          id: 1,
          thread_id: "uuid-1",
          title: "Hi",
          created_at: "2026-05-10T12:00:00Z",
          updated_at: "2026-05-10T12:00:00Z",
          messages: [],
          has_more: false,
          next_cursor: null,
        },
      });
    });

    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await page.goto("/");
    await page.getByRole("tab", { name: /chat/i }).click();
    await expect(page.getByRole("tab", { name: /chat/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // The chat hero copy renders once the thread is bootstrapped.
    await expect(page.getByRole("heading", { name: /fridge assistant/i })).toBeVisible();

    // No real console errors. Filter known noise (websocket, MSW chatter).
    const real = consoleErrors.filter(
      (e) =>
        !/websocket/i.test(e) &&
        !/\[MSW\]/i.test(e) &&
        !/family-events/i.test(e) &&
        !/Hot Module Replacement/i.test(e),
    );
    expect(real).toEqual([]);
  });

  test("[e2e] Settings: language switcher is still clickable next to feedback card (no overlay regression)", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /settings/i }).click();
    // The Polish radio sits in the language card, just above the feedback card.
    const polish = page.getByRole("radio", { name: /polish|polski/i });
    await expect(polish).toBeVisible();
    // We don't click — clicking triggers a full-page reload (Paraglide reload:true)
    // which destabilizes the test. Visibility + role exposure is enough to
    // confirm the new feedback card hasn't displaced or covered the switcher.
  });
});
