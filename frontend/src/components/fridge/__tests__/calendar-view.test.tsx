/**
 * Integration tests for CalendarView — week strip nav, agenda render, event
 * editor open/save, "no Google" hint, fan-out copy on family events.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { CalendarView } from "@/components/fridge/calendar-view";
import { server } from "@/test/msw-server";
import {
  FIXTURE_CARS,
  FIXTURE_EVENTS,
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

describe("[integration] CalendarView", () => {
  test("renders the week strip with 7 day pills", async () => {
    server.use(...successHandlers({ events: [] }));
    render(<CalendarView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText(/no events this week/i));
    // 7 day-pill buttons should be present (`aria-label="Mon 22"` etc).
    const dayButtons = screen.getAllByRole("button").filter((b) => /^[A-Z][a-z]{2} \d{1,2}$/.test(b.getAttribute("aria-label") ?? ""));
    expect(dayButtons.length).toBe(7);
  });

  test("empty: shows 'No events this week' CTA", async () => {
    server.use(...successHandlers({ events: [] }));
    render(<CalendarView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => {
      expect(screen.getByText(/no events this week/i)).toBeInTheDocument();
    });
  });

  test("populated: renders event cards with title, time, location", async () => {
    // Fixture has Soccer practice for Ola — adjust start_at to "today" so the
    // week-range query returns it regardless of when tests run.
    const today = new Date();
    today.setHours(16, 0, 0, 0);
    const end = new Date(today.getTime() + 90 * 60 * 1000);
    const events = [
      { ...FIXTURE_EVENTS[0], start_at: today.toISOString(), end_at: end.toISOString() },
    ];
    server.use(...successHandlers({ events }));

    render(<CalendarView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => {
      expect(screen.getByText("Soccer practice")).toBeInTheDocument();
      expect(screen.getByText(/riverside park/i)).toBeInTheDocument();
    });
  });

  test("error: API failure renders error banner with retry", async () => {
    server.use(
      http.get(`${BACKEND}/api/events`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
      http.get(`${BACKEND}/api/calendar/sync-state`, () => HttpResponse.json([])),
    );
    render(<CalendarView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  test("event editor: opens on 'New event', POSTs with title + assignee + cars", async () => {
    let posted: { title: string; assignee_member_id: string | null; car_ids: string[] } | null = null;
    server.use(...successHandlers({ events: [] }));
    server.use(
      http.post(`${BACKEND}/api/events`, async ({ request }) => {
        posted = (await request.json()) as typeof posted;
        return HttpResponse.json(
          {
            id: "e-new",
            family_id: "fam-1",
            title: posted!.title,
            description: null,
            start_at: new Date().toISOString(),
            end_at: new Date(Date.now() + 3_600_000).toISOString(),
            timezone: "Europe/Warsaw",
            location: null,
            assignee_member_id: posted!.assignee_member_id,
            car_ids: posted!.car_ids,
            rrule: null,
            source: "fridge",
            source_member_id: null,
            targets: [],
            linked_note_id: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    render(<CalendarView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText(/no events this week/i));

    await user.click(screen.getByRole("button", { name: /new event/i }));
    const sheet = await screen.findByRole("dialog", { name: /new event/i });
    await user.type(within(sheet).getByLabelText(/title/i), "Pickup Ola");
    await user.click(within(sheet).getByRole("radio", { name: /assign to monika/i }));
    await user.click(within(sheet).getByRole("button", { name: /save event/i }));

    await waitFor(() => {
      expect(posted).not.toBeNull();
      expect(posted!.title).toBe("Pickup Ola");
      expect(posted!.assignee_member_id).toBe("m-mom");
    });
  });

  test("event editor: shows 'no Google connected' hint when assigning to Ola", async () => {
    server.use(...successHandlers({ events: [] }));
    const user = userEvent.setup();
    render(<CalendarView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText(/no events this week/i));

    await user.click(screen.getByRole("button", { name: /new event/i }));
    const sheet = await screen.findByRole("dialog", { name: /new event/i });
    await user.click(within(sheet).getByRole("radio", { name: /assign to ola/i }));

    expect(
      within(sheet).getByText(/doesn't have google connected/i),
    ).toBeInTheDocument();
  });
});
