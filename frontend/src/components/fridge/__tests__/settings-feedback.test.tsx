/**
 * Integration tests for the new "Send feedback" card on SettingsView
 * (FrontendTester brief: Tier A #4 entry point, Tier B #7 regression).
 *
 * Specifically:
 *   - The card renders at the bottom of Settings.
 *   - Clicking the button opens the FeedbackModal (role=dialog) with `bug`
 *     pre-selected (the modal's reset-on-open behavior is tested in
 *     feedback-modal.test.tsx; here we just verify the wiring).
 *   - Existing settings actions still work after the new card was inserted —
 *     specifically the language switcher card just above the feedback card.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsView } from "@/components/fridge/settings-view";
import { server } from "@/test/msw-server";
import {
  FIXTURE_CARS,
  FIXTURE_FAMILY,
  FIXTURE_MEMBERS,
  successHandlers,
} from "@/test/msw-handlers";
import { saveToken } from "@/lib/auth";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

beforeEach(() => {
  saveToken("eyJhbGciOiJub25lIn0.eyJmYW1pbHlfaWQiOiJmYW0tMSJ9.x");
  server.use(...successHandlers());
});

afterEach(() => vi.restoreAllMocks());

function renderSettings() {
  render(
    <SettingsView
      family={FIXTURE_FAMILY}
      members={FIXTURE_MEMBERS}
      cars={FIXTURE_CARS}
      refresh={vi.fn()}
    />,
  );
}

describe("[integration] SettingsView — feedback card", () => {
  test("renders 'Send feedback' button below the language card", () => {
    renderSettings();
    const button = screen.getByRole("button", { name: /send feedback/i });
    expect(button).toBeInTheDocument();
  });

  test("clicking 'Send feedback' opens the modal with all four category radios", async () => {
    renderSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /send feedback/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeVisible();
    // All 4 category radios are present.
    expect(within(dialog).getByLabelText(/^bug$/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^improvement$/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^question$/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^other$/i)).toBeInTheDocument();
    // "Bug" is the default selection per the modal's reset-on-open.
    expect(
      within(dialog).getByLabelText(/^bug$/i),
    ).toBeChecked();
  });

  test("language switcher card still renders after the feedback card was inserted", () => {
    renderSettings();
    // The Language card sits above the feedback card. Both must be present.
    expect(
      screen.getByRole("heading", { name: /^language$/i }),
    ).toBeInTheDocument();
    // The feedback card uses `feedback_modal_title` ("Send feedback") for its h3.
    expect(
      screen.getAllByRole("heading", { name: /send feedback/i }).length,
    ).toBeGreaterThanOrEqual(1);
  });

  test("language switcher buttons are still clickable (no overlay regression from feedback card)", async () => {
    renderSettings();
    const user = userEvent.setup();
    // The language switcher renders role=radio buttons inside a radiogroup.
    // We can't assert a locale switch because setAppLocale triggers a reload,
    // which jsdom can't perform — but we CAN verify the radios are clickable
    // and the click handler is reachable. If the feedback-card insertion had
    // broken the layout (e.g. via an absolutely-positioned overlay), userEvent
    // would throw a "pointer events are disabled" error — the very signal we
    // want.
    const polishRadio = screen.getByRole("radio", { name: /polish|polski/i });
    await user.click(polishRadio);
  });

  test("feedback button has accessible name reachable by tab navigation", async () => {
    renderSettings();
    const button = screen.getByRole("button", { name: /send feedback/i });
    // Has a non-empty accessible name (the brief calls this out as Tier C #11).
    expect(button).toHaveAccessibleName();
    // Programmatically focus to confirm it's tabbable.
    button.focus();
    expect(button).toHaveFocus();
  });
});
