/**
 * Integration tests for NotesView — render with MSW backing the API and assert
 * UI behavior across loading / empty / populated / error / mutation paths.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { NotesView } from "@/components/fridge/notes-view";
import { server } from "@/test/msw-server";
import {
  FIXTURE_CARS,
  FIXTURE_MEMBERS,
  FIXTURE_NOTES,
  successHandlers,
} from "@/test/msw-handlers";
import { saveToken } from "@/lib/auth";

const BACKEND = "http://localhost:8001";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

beforeEach(() => {
  // Hook reads token to build the WS URL — give it a benign one.
  saveToken("eyJhbGciOiJub25lIn0.eyJmYW1pbHlfaWQiOiJmYW0tMSJ9.x");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("[integration] NotesView", () => {
  test("loading: shows skeleton then renders pinned and recent sections", async () => {
    server.use(...successHandlers());
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);

    expect(screen.getByLabelText(/quick-add a note/i)).toBeInTheDocument();
    await waitFor(() => {
      // Two pinned notes and one recent in fixture
      expect(screen.getByText("Shopping list")).toBeInTheDocument();
      expect(screen.getByText("Take out trash Mon 8am")).toBeInTheDocument();
      expect(screen.getByText("Dentist appt for Ola")).toBeInTheDocument();
    });
  });

  test("empty: shows empty-board CTA when API returns no notes", async () => {
    server.use(...successHandlers({ notes: [] }));
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => {
      expect(screen.getByText(/this board is empty/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /new note/i })).toBeInTheDocument();
  });

  test("error: 500 on /notes shows error banner with a retry button", async () => {
    server.use(
      http.get(`${BACKEND}/notes`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  test("retry: clicking Retry refetches and clears the error", async () => {
    let calls = 0;
    server.use(
      http.get(`${BACKEND}/notes`, () => {
        calls += 1;
        if (calls === 1)
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        return HttpResponse.json({ items: FIXTURE_NOTES, total: FIXTURE_NOTES.length });
      }),
    );
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByRole("alert"));
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => {
      expect(screen.getByText("Shopping list")).toBeInTheDocument();
    });
  });

  test("add-note: typing and clicking Add posts and prepends the new note", async () => {
    let postedBody: { content: string; assignee_member_id: string | null } | null =
      null;
    server.use(...successHandlers({ notes: [] }));
    // Override goes in a SECOND server.use() call so MSW prepends it and our
    // POST handler beats the default success POST handler to the request.
    server.use(
      http.post(`${BACKEND}/notes`, async ({ request }) => {
        postedBody = (await request.json()) as typeof postedBody;
        return HttpResponse.json(
          {
            id: "n-new",
            family_id: "fam-1",
            content: postedBody!.content,
            icon: null,
            labels: [],
            pinned: false,
            assignee_member_id: postedBody!.assignee_member_id,
            car_ids: [],
            linked_event_id: null,
            created_at: "2026-04-24T12:00:00Z",
            updated_at: "2026-04-24T12:00:00Z",
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText(/this board is empty/i));

    const input = screen.getByLabelText(/quick-add a note/i);
    await user.type(input, "Buy oat milk");
    await user.click(screen.getByRole("button", { name: /^add$/i }));
    await waitFor(() => {
      expect(postedBody).not.toBeNull();
      expect(postedBody!.content).toBe("Buy oat milk");
      expect(postedBody!.assignee_member_id).toBeNull(); // family-wide default
    });
    await waitFor(() => {
      expect(screen.getByText("Buy oat milk")).toBeInTheDocument();
    });
  });

  test("assignee selection: picking a member sets assignee_member_id on the create call", async () => {
    let postedBody: { assignee_member_id: string | null } | null = null;
    server.use(...successHandlers({ notes: [] }));
    server.use(
      http.post(`${BACKEND}/notes`, async ({ request }) => {
        postedBody = (await request.json()) as typeof postedBody;
        return HttpResponse.json(
          {
            id: "n-new",
            family_id: "fam-1",
            content: "x",
            icon: null,
            labels: [],
            pinned: false,
            assignee_member_id: postedBody!.assignee_member_id,
            car_ids: [],
            linked_event_id: null,
            created_at: "2026-04-24T12:00:00Z",
            updated_at: "2026-04-24T12:00:00Z",
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText(/this board is empty/i));

    await user.click(screen.getByRole("radio", { name: /assign to ola/i }));
    const input = screen.getByLabelText(/quick-add a note/i);
    await user.type(input, "x");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    await waitFor(() => {
      expect(postedBody).not.toBeNull();
      expect(postedBody!.assignee_member_id).toBe("m-ola");
    });
  });

  test("checklist toggle: clicking a shopping-list item PATCHes with new content", async () => {
    let patchedBody: { content?: string } | null = null;
    server.use(...successHandlers());
    server.use(
      http.patch(`${BACKEND}/notes/n-shopping`, async ({ request }) => {
        patchedBody = (await request.json()) as typeof patchedBody;
        return HttpResponse.json({
          ...FIXTURE_NOTES[0],
          content: patchedBody!.content!,
          updated_at: "2026-04-24T12:00:00Z",
        });
      }),
    );
    const user = userEvent.setup();
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText("Shopping list"));

    // Toggle the first item ("milk" → checked).
    const items = screen.getAllByRole("checkbox");
    const milkItem = items.find((el) => el.textContent === "milk");
    expect(milkItem).toBeDefined();
    await user.click(milkItem!);

    await waitFor(() => {
      expect(patchedBody?.content).toBe("[x] milk\n[ ] bread\n[x] coffee");
    });
  });

  test("a11y: assignee picker uses radiogroup semantics with one selected radio", async () => {
    server.use(...successHandlers());
    render(<NotesView members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    await waitFor(() => screen.getByText("Shopping list"));

    const group = screen.getByRole("radiogroup", { name: /assign to a family member/i });
    const radios = within(group).getAllByRole("radio");
    expect(radios.length).toBeGreaterThan(1);
    const checked = radios.filter(
      (r) => r.getAttribute("aria-checked") === "true",
    );
    expect(checked.length).toBe(1);
  });
});
