/**
 * Integration tests for SettingsView — members CRUD, cars CRUD, preferences.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { SettingsView } from "@/components/fridge/settings-view";
import { server } from "@/test/msw-server";
import {
  FIXTURE_CARS,
  FIXTURE_FAMILY,
  FIXTURE_MEMBERS,
  successHandlers,
} from "@/test/msw-handlers";
import { saveToken } from "@/lib/auth";

const BACKEND = "http://localhost:8001";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

beforeEach(() => {
  saveToken("eyJhbGciOiJub25lIn0.eyJmYW1pbHlfaWQiOiJmYW0tMSJ9.x");
});

afterEach(() => vi.restoreAllMocks());

function renderSettings(overrides?: { members?: typeof FIXTURE_MEMBERS }) {
  const refresh = vi.fn();
  render(
    <SettingsView
      family={FIXTURE_FAMILY}
      members={overrides?.members ?? FIXTURE_MEMBERS}
      cars={FIXTURE_CARS}
      refresh={refresh}
    />,
  );
  return { refresh };
}

describe("[integration] SettingsView — members", () => {
  test("renders the active member list with names and Google statuses", async () => {
    server.use(...successHandlers());
    renderSettings();
    await waitFor(() => screen.getByText("Monika"));
    expect(screen.getByText("Szymon")).toBeInTheDocument();
    expect(screen.getByText("Ola")).toBeInTheDocument();
    expect(screen.getAllByText(/google synced/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/no google account yet/i)).toBeInTheDocument();
  });

  test("opens AddMemberSheet when the add button is tapped, saves a new member", async () => {
    let postedBody: { name: string; color: string; nickname: string | null } | null = null;
    server.use(...successHandlers());
    server.use(
      http.post(`${BACKEND}/api/members`, async ({ request }) => {
        postedBody = (await request.json()) as typeof postedBody;
        return HttpResponse.json(
          {
            id: "m-new",
            family_id: "fam-1",
            name: postedBody!.name,
            nickname: postedBody!.nickname,
            color: postedBody!.color,
            status: "active",
            is_setup_owner: false,
            google: { status: "not_connected", email: null, connected_at: null },
            created_at: new Date().toISOString(),
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: /add a family member/i }));

    const dialog = await screen.findByRole("dialog", { name: /add a family member/i });
    // The "Name (required)" label matches /^name/i; the nickname label would
    // also match /name/i so we anchor.
    const nameInput = within(dialog).getByLabelText(/^name/i);
    await user.type(nameInput, "Wojtek");
    await user.click(within(dialog).getByRole("button", { name: /save member/i }));

    await waitFor(() => {
      expect(postedBody).not.toBeNull();
      expect(postedBody!.name).toBe("Wojtek");
    });
  });

  test("set inactive opens a confirm dialog and POSTs to set-inactive on confirm", async () => {
    let setInactiveCalled = false;
    server.use(...successHandlers());
    server.use(
      http.post(`${BACKEND}/api/members/m-ola/set-inactive`, () => {
        setInactiveCalled = true;
        return HttpResponse.json({ ...FIXTURE_MEMBERS[2], status: "inactive" });
      }),
    );
    const user = userEvent.setup();
    renderSettings();

    await user.click(
      screen.getByRole("button", { name: /set ola inactive/i }),
    );
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/set ola inactive/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /^set inactive$/i }));

    await waitFor(() => expect(setInactiveCalled).toBe(true));
  });

  test("a11y: confirm dialog uses role=alertdialog with aria-modal", async () => {
    server.use(...successHandlers());
    const user = userEvent.setup();
    renderSettings();

    await user.click(
      screen.getByRole("button", { name: /set ola inactive/i }),
    );
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });
});

describe("[integration] SettingsView — cars", () => {
  test("delete car permanently shows destructive confirm and DELETEs on confirm", async () => {
    let deleted = false;
    server.use(...successHandlers());
    server.use(
      http.delete(`${BACKEND}/api/cars/c-civic`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderSettings();
    // Open the per-row "more actions" menu for Red Civic
    await user.click(
      screen.getByRole("button", { name: /more actions for red civic/i }),
    );
    await user.click(screen.getByRole("menuitem", { name: /delete permanently/i }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/delete red civic/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /^delete permanently$/i }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  test("opens add-car sheet, fills required name and saves", async () => {
    let posted: { name: string; year: number | null } | null = null;
    server.use(...successHandlers());
    server.use(
      http.post(`${BACKEND}/api/cars`, async ({ request }) => {
        posted = (await request.json()) as typeof posted;
        return HttpResponse.json(
          {
            id: "c-new",
            family_id: "fam-1",
            name: posted!.name,
            year: posted!.year,
            color_label: null,
            color: "stone",
            notes: null,
            status: "active",
            created_at: new Date().toISOString(),
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByRole("button", { name: /add a car/i }));
    const dialog = await screen.findByRole("dialog", { name: /add a car/i });
    await user.type(within(dialog).getByLabelText(/^name/i), "Scooter");
    await user.type(within(dialog).getByLabelText(/year/i), "2022");
    await user.click(within(dialog).getByRole("button", { name: /save car/i }));

    await waitFor(() => {
      expect(posted?.name).toBe("Scooter");
      expect(posted?.year).toBe(2022);
    });
  });
});

describe("[integration] SettingsView — preferences", () => {
  test("toggles fan-out preference and PATCHes /api/family/preferences", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(...successHandlers());
    server.use(
      http.patch(`${BACKEND}/api/family/preferences`, async ({ request }) => {
        patched = (await request.json()) as typeof patched;
        return HttpResponse.json({
          family_id: "fam-1",
          sync_interval_sec: 300,
          fanout_enabled: false,
          voice_wake_enabled: false,
          always_on: true,
          auto_create_shopping_list: true,
          updated_at: new Date().toISOString(),
        });
      }),
    );
    const user = userEvent.setup();
    renderSettings();

    const toggle = await screen.findByRole("switch", { name: /fan-out family events/i });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await user.click(toggle);
    await waitFor(() => {
      expect(patched).not.toBeNull();
      expect(patched!.fanout_enabled).toBe(false);
    });
  });

  test("voice wake toggle is disabled (per design doc — v1.1 placeholder)", async () => {
    server.use(...successHandlers());
    renderSettings();
    const toggle = await screen.findByRole("switch", { name: /voice wake phrase/i });
    expect(toggle).toBeDisabled();
  });
});
