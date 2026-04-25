/**
 * Shared types for the /design-preview tree.
 *
 * These mirror the per-feature spec data models at the UI level — but they are
 * UI-only mocks. The Architect owns the real schema; the Developer should
 * align these props against whatever the backend exposes.
 */

export type MemberColor =
  | "sage"
  | "blue"
  | "blush"
  | "butter"
  | "stone"
  | "lavender"
  | "seafoam";

export const MEMBER_COLOR_HEX: Record<MemberColor, string> = {
  sage: "#C7D4B6",
  blue: "#B9C7D4",
  blush: "#E4C7C2",
  butter: "#E8DDB5",
  stone: "#D4C9B9",
  lavender: "#C8C2D4",
  seafoam: "#B9D4CC",
};

/** Maps a MemberColor to the assignedXxx CSS module class on the .note element. */
export const NOTE_ASSIGNED_CLASS: Record<MemberColor, string> = {
  sage: "assignedSage",
  blue: "assignedBlue",
  blush: "assignedBlush",
  butter: "assignedButter",
  stone: "assignedStone",
  lavender: "assignedStone",
  seafoam: "assignedSage",
};

/** Maps a MemberColor to the eventCard left-rail variant class. */
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

export type GoogleConnectionState =
  | "connected"
  | "pending" // not connected yet
  | "reconnect-needed"
  | "inactive";

export interface Member {
  id: string;
  name: string;
  nickname?: string;
  email?: string;
  initials: string;
  color: MemberColor;
  status: "active" | "inactive";
  google: GoogleConnectionState;
  isSetupOwner?: boolean;
}

export interface Car {
  id: string;
  name: string;
  year?: number;
  colorLabel?: string;
  notes?: string;
  color: MemberColor;
  status: "active" | "inactive";
}

export type Assignee =
  | { kind: "member"; id: string }
  | { kind: "car"; id: string }
  | { kind: "family-wide" };

export interface Note {
  id: string;
  icon?: string; // lucide icon name
  title?: string;
  body?: string;
  /** When set, the note renders as a checklist (shopping-list semantics). */
  checklist?: { text: string; done: boolean }[];
  labels: string[];
  pinned: boolean;
  linkedEventId?: string;
  carLabels?: string[]; // car ids appended as label chips
  assignee?: Assignee;
  span?: 1 | 2;
}

export interface CalendarEvent {
  id: string;
  title: string;
  startAt: Date;
  endAt: Date;
  location?: string;
  rrule?: string;
  rruleLabel?: string; // human label e.g. "Recurring · Mon/Wed"
  assignees: Assignee[];
  fanout?: boolean;
  fanoutLabel?: string;
  syncStatus?: "synced" | "pending" | "failed";
  linkedNoteId?: string;
  /** Computed left-rail color: member color OR "family" for fan-out. */
  railColor: MemberColor | "family";
}

export interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: React.ReactNode;
  authorMemberId?: string;
  toolCalls?: ToolCall[];
}

export interface ToolCall {
  id: string;
  toolName: string;
  label: string; // "Read notes", "Update note"
  text: string; // "Found 2 notes…"
  status: "pending" | "done" | "failed";
}

export interface FamilyPrefs {
  syncIntervalMinutes: 1 | 5 | 15;
  fanoutEnabled: boolean;
  voiceWakeEnabled: boolean;
  alwaysOn: boolean;
}
