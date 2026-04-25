/**
 * A11y tests for BottomTabNav — role=tablist, tab aria-selected, click handling.
 */
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BottomTabNav } from "@/components/fridge/bottom-tab-nav";

describe("[a11y] BottomTabNav", () => {
  test("renders as role=tablist with 4 tabs in Chat / Notes / Calendar / Settings order", () => {
    render(<BottomTabNav active="notes" onChange={() => undefined} />);
    const list = screen.getByRole("tablist", { name: /primary navigation/i });
    const tabs = screen.getAllByRole("tab");
    expect(list).toBeInTheDocument();
    expect(tabs.map((t) => t.textContent)).toEqual(["Chat", "Notes", "Calendar", "Settings"]);
  });

  test("marks the active tab with aria-selected=true and inactive with false", () => {
    render(<BottomTabNav active="notes" onChange={() => undefined} />);
    const notesTab = screen.getByRole("tab", { name: /notes/i });
    const chatTab = screen.getByRole("tab", { name: /chat/i });
    expect(notesTab).toHaveAttribute("aria-selected", "true");
    expect(chatTab).toHaveAttribute("aria-selected", "false");
  });

  test("clicking a tab invokes onChange with that tab key", async () => {
    const onChange = vi.fn();
    render(<BottomTabNav active="notes" onChange={onChange} />);
    await userEvent.setup().click(screen.getByRole("tab", { name: /calendar/i }));
    expect(onChange).toHaveBeenCalledWith("calendar");
  });

  test("badges render as aria-labelled with the count", () => {
    render(<BottomTabNav active="notes" onChange={() => undefined} badges={{ chat: 3 }} />);
    expect(screen.getByLabelText(/3 new/i)).toHaveTextContent("3");
  });

  test("tab aria-controls references the matching view id", () => {
    render(<BottomTabNav active="notes" onChange={() => undefined} />);
    const notesTab = screen.getByRole("tab", { name: /notes/i });
    expect(notesTab).toHaveAttribute("aria-controls", "view-notes");
    expect(notesTab).toHaveAttribute("id", "tab-notes");
  });
});
