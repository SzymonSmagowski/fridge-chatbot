/**
 * Component unit tests for NoteCard — renders different variants based on note
 * shape (assigned, family-wide, pinned, linked-event, shopping checklist).
 */
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NoteCard } from "@/components/fridge/note-card";
import { FIXTURE_CARS, FIXTURE_MEMBERS, FIXTURE_NOTES } from "@/test/msw-handlers";
import type { NoteResponse } from "@/lib/api";

const base: NoteResponse = {
  id: "n-1",
  family_id: "fam-1",
  content: "Trash Mon 8am",
  icon: null,
  labels: [],
  pinned: false,
  assignee_member_id: null,
  car_ids: [],
  linked_event_id: null,
  created_at: "2026-04-20T00:00:00Z",
  updated_at: "2026-04-20T00:00:00Z",
};

describe("[unit] NoteCard", () => {
  test("family-wide (no assignee) renders 'Family-wide' footer", () => {
    render(<NoteCard note={base} members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    expect(screen.getByText(/family-wide/i)).toBeInTheDocument();
  });

  test("assigned-to-member renders the member name and initials", () => {
    const note = { ...base, assignee_member_id: "m-ola" };
    render(<NoteCard note={note} members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    expect(screen.getByText("Ola")).toBeInTheDocument();
  });

  test("pinned note renders the Pinned aria label", () => {
    const note = { ...base, pinned: true };
    render(<NoteCard note={note} members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    expect(screen.getByLabelText(/pinned/i)).toBeInTheDocument();
  });

  test("linked_event_id adds the 'Recurring event' chip", () => {
    const note = { ...base, linked_event_id: "e-soccer" };
    render(<NoteCard note={note} members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    expect(screen.getByText(/recurring event/i)).toBeInTheDocument();
  });

  test("shopping-list label renders body as a checklist of checkbox rows", () => {
    // Use the fixture's shopping list note directly
    render(<NoteCard note={FIXTURE_NOTES[0]} members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    const items = screen.getAllByRole("checkbox");
    expect(items.length).toBe(3);
    expect(items[0]).toHaveTextContent("milk");
    expect(items[0]).toHaveAttribute("aria-checked", "false");
    expect(items[2]).toHaveAttribute("aria-checked", "true"); // `[x] coffee`
  });

  test("checklist item keyboard: pressing Space toggles via onToggleChecklist", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    render(
      <NoteCard
        note={FIXTURE_NOTES[0]}
        members={FIXTURE_MEMBERS}
        cars={FIXTURE_CARS}
        onToggleChecklist={onToggle}
      />,
    );
    const items = screen.getAllByRole("checkbox");
    items[1].focus();
    await user.keyboard(" ");
    expect(onToggle).toHaveBeenCalledWith("n-shopping", 1);
  });

  test("labels render as #display-name chips", () => {
    const note = {
      ...base,
      labels: [
        { slug: "reminder", display_name: "Reminder" },
        { slug: "errand", display_name: "Errand" },
      ],
    };
    render(<NoteCard note={note} members={FIXTURE_MEMBERS} cars={FIXTURE_CARS} />);
    expect(screen.getByText("#Reminder")).toBeInTheDocument();
    expect(screen.getByText("#Errand")).toBeInTheDocument();
  });
});
