/**
 * Shared UI types for the fridge production tree.
 * Mirrors Architect's API contract (§5) where it intersects with the UI.
 */

export type MemberColor =
  | "sage"
  | "blue"
  | "blush"
  | "butter"
  | "stone"
  | "lavender"
  | "seafoam";

export const MEMBER_COLORS: MemberColor[] = [
  "sage",
  "blue",
  "blush",
  "butter",
  "stone",
  "lavender",
  "seafoam",
];

export const MEMBER_COLOR_HEX: Record<MemberColor, string> = {
  sage: "#C7D4B6",
  blue: "#B9C7D4",
  blush: "#E4C7C2",
  butter: "#E8DDB5",
  stone: "#D4C9B9",
  lavender: "#C8C2D4",
  seafoam: "#B9D4CC",
};

/** Maps a MemberColor to a CSS module class name on .note. */
export const NOTE_ASSIGNED_CLASS: Record<MemberColor, string> = {
  sage: "assignedSage",
  blue: "assignedBlue",
  blush: "assignedBlush",
  butter: "assignedButter",
  stone: "assignedStone",
  lavender: "assignedStone",
  seafoam: "assignedSage",
};

/** Maps a member/family rail to event-card variant class. */
export const EVENT_RAIL_CLASS: Record<MemberColor | "family", string> = {
  sage: "",
  blue: "blue",
  blush: "blush",
  butter: "butter",
  stone: "stone",
  lavender: "stone",
  seafoam: "",
  family: "family",
};

export function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p.charAt(0).toUpperCase()).join("") || "??";
}
