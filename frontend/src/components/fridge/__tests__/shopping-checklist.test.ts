import { describe, expect, test } from "vitest";
import {
  appendChecklistLine,
  parseChecklist,
  serializeChecklist,
  toggleChecklistAt,
} from "../shopping-checklist";

describe("[unit] shopping-checklist parser", () => {
  test("parseChecklist treats `[x] foo` as done", () => {
    const items = parseChecklist("[x] milk");
    expect(items).toEqual([{ text: "milk", done: true }]);
  });

  test("parseChecklist treats `[ ] foo` as not done", () => {
    const items = parseChecklist("[ ] milk");
    expect(items).toEqual([{ text: "milk", done: false }]);
  });

  test("parseChecklist treats bare lines as not done", () => {
    const items = parseChecklist("milk\nbread");
    expect(items).toEqual([
      { text: "milk", done: false },
      { text: "bread", done: false },
    ]);
  });

  test("parseChecklist skips blank lines", () => {
    expect(parseChecklist("\n\n[x] milk\n\n")).toEqual([
      { text: "milk", done: true },
    ]);
  });

  test("parseChecklist is case-insensitive for the `X` marker", () => {
    expect(parseChecklist("[X] milk")).toEqual([{ text: "milk", done: true }]);
  });

  test("serializeChecklist round-trips through parseChecklist", () => {
    const original = "[x] coffee\n[ ] eggs\n[ ] bread";
    expect(serializeChecklist(parseChecklist(original))).toBe(original);
  });

  test("toggleChecklistAt flips the targeted item", () => {
    const next = toggleChecklistAt("[ ] milk\n[x] bread", 0);
    expect(next).toBe("[x] milk\n[x] bread");
  });

  test("toggleChecklistAt flips a done item back to pending", () => {
    const next = toggleChecklistAt("[x] coffee", 0);
    expect(next).toBe("[ ] coffee");
  });

  test("toggleChecklistAt is a no-op for out-of-range indices", () => {
    const original = "[ ] milk";
    expect(toggleChecklistAt(original, 5)).toBe(original);
    expect(toggleChecklistAt(original, -1)).toBe(original);
  });

  test("appendChecklistLine appends as unchecked", () => {
    expect(appendChecklistLine("[ ] milk", "bread")).toBe("[ ] milk\n[ ] bread");
  });

  test("appendChecklistLine seeds an empty content correctly", () => {
    expect(appendChecklistLine("", "milk")).toBe("[ ] milk");
  });

  test("appendChecklistLine ignores whitespace-only lines", () => {
    const original = "[ ] milk";
    expect(appendChecklistLine(original, "   ")).toBe(original);
  });
});
