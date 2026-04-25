/**
 * Mock data that exercises every journey from the four feature specs.
 *
 * - members.md: 3 active members + 1 with no Google + connect flow
 * - notes.md: pinned shopping list, family-wide & assigned notes,
 *             linked-event chip, car label chip, recent grid
 * - google-calendar.md: single-member event, fan-out family event,
 *             recurring event, car-only event, sync status per member
 * - cars.md: 3 cars with optional fields, soft + hard delete affordances
 *
 * The Architect/Developer should replace this with real fetch calls; the
 * shapes here mirror the intent of each spec but are not the schema.
 */

import type { CalendarEvent, Car, ChatMessage, FamilyPrefs, Member, Note } from "./types";

export const MOCK_FAMILY_NAME = "The Magowski Family";
export const MOCK_FAMILY_INITIAL = "M";
export const MOCK_FAMILY_CREATED = "January 14, 2026";

export const MOCK_MEMBERS: Member[] = [
  {
    id: "m_mom",
    name: "Monika",
    nickname: "Mom",
    email: "monika@gmail.com",
    initials: "MO",
    color: "blue",
    status: "active",
    google: "connected",
  },
  {
    id: "m_dad",
    name: "Szymon",
    nickname: "Dad",
    email: "smagowski.szymon@gmail.com",
    initials: "DA",
    color: "blush",
    status: "active",
    google: "connected",
    isSetupOwner: true,
  },
  {
    id: "m_ola",
    name: "Ola",
    initials: "OL",
    color: "sage",
    status: "active",
    google: "pending",
  },
  {
    id: "m_grandma",
    name: "Grandma Eva",
    initials: "EV",
    color: "butter",
    status: "inactive",
    google: "inactive",
  },
];

export const ACTIVE_MEMBERS = MOCK_MEMBERS.filter((m) => m.status === "active");

export const MOCK_CARS: Car[] = [
  {
    id: "c_volvo",
    name: "Family Volvo",
    year: 2019,
    colorLabel: "White",
    color: "stone",
    status: "active",
  },
  {
    id: "c_civic",
    name: "Red Civic",
    year: 2015,
    colorLabel: "Red",
    notes: "At Pete's Garage",
    color: "blush",
    status: "active",
  },
  {
    id: "c_scooter",
    name: "Ola's Scooter",
    notes: "Electric",
    color: "butter",
    status: "active",
  },
];

export const MOCK_NOTES: Note[] = [
  {
    id: "n_shopping",
    title: "Shopping list",
    icon: "shopping-cart",
    labels: ["#shopping-list", "family"],
    checklist: [
      { text: "Milk", done: true },
      { text: "Eggs (dozen)", done: false },
      { text: "Sourdough", done: false },
      { text: "Romaine + tomatoes", done: false },
      { text: "Coffee beans", done: false },
      { text: "Apples (gala)", done: false },
    ],
    pinned: true,
    span: 2,
    assignee: { kind: "family-wide" },
  },
  {
    id: "n_trash",
    title: "Trash & recycling",
    body: "Bins out by 7am Monday. Green bin this week.",
    icon: "trash-2",
    labels: ["recurring"],
    pinned: true,
    linkedEventId: "e_trash",
    assignee: { kind: "member", id: "m_dad" },
  },
  {
    id: "n_field",
    title: "Field trip slip",
    body: "Ola's permission slip for the science museum trip — sign and return by Friday.",
    icon: "file-text",
    labels: ["school"],
    pinned: true,
    assignee: { kind: "member", id: "m_ola" },
  },
  {
    id: "n_dentist",
    title: "Dentist Thu 10am",
    body: "Dr. Carter's office, insurance card on fridge.",
    icon: "calendar",
    labels: ["health"],
    pinned: false,
    assignee: { kind: "member", id: "m_mom" },
  },
  {
    id: "n_civic",
    title: "Civic at Pete's",
    body: "Red Civic is at Pete's garage — oil change + new tires. Ready Thursday.",
    icon: "car",
    labels: [],
    carLabels: ["c_civic"],
    pinned: false,
    assignee: { kind: "car", id: "c_civic" },
  },
  {
    id: "n_amazon",
    title: "Pick up Amazon package",
    body: "Locker at Whole Foods, code 4421. Expires Sat 9pm.",
    icon: "package",
    labels: ["errand"],
    pinned: false,
    assignee: { kind: "member", id: "m_dad" },
  },
];

const today = new Date();
today.setHours(16, 0, 0, 0);
const todayPlus = (h: number, m = 0) => {
  const d = new Date(today);
  d.setHours(h, m, 0, 0);
  return d;
};
const dayOffset = (offset: number, h: number, m = 0) => {
  const d = new Date(today);
  d.setDate(d.getDate() + offset);
  d.setHours(h, m, 0, 0);
  return d;
};

export const MOCK_EVENTS: CalendarEvent[] = [
  {
    id: "e_soccer",
    title: "Soccer practice",
    startAt: todayPlus(16, 0),
    endAt: todayPlus(17, 0),
    location: "Riverside Park, Field 3",
    rruleLabel: "Recurring · Mon/Wed",
    assignees: [{ kind: "member", id: "m_ola" }],
    syncStatus: "synced",
    railColor: "sage",
  },
  {
    id: "e_dinner",
    title: "Dinner with the Smiths",
    startAt: todayPlus(19, 0),
    endAt: todayPlus(21, 0),
    location: "Our house",
    fanout: true,
    fanoutLabel: "Synced to 3 calendars",
    assignees: [
      { kind: "member", id: "m_mom" },
      { kind: "member", id: "m_dad" },
      { kind: "member", id: "m_ola" },
    ],
    syncStatus: "synced",
    railColor: "family",
  },
  {
    id: "e_trash",
    title: "Trash & recycling (green bin)",
    startAt: dayOffset(1, 8, 0),
    endAt: dayOffset(1, 8, 30),
    rruleLabel: "Weekly",
    linkedNoteId: "n_trash",
    assignees: [{ kind: "member", id: "m_dad" }],
    syncStatus: "synced",
    railColor: "blush",
  },
  {
    id: "e_dentist",
    title: "Dentist — Dr. Carter",
    startAt: dayOffset(1, 10, 0),
    endAt: dayOffset(1, 11, 0),
    location: "Mountain View Dental",
    assignees: [{ kind: "member", id: "m_mom" }],
    syncStatus: "synced",
    railColor: "blue",
  },
  {
    id: "e_volvo",
    title: "Volvo service appointment",
    startAt: dayOffset(3, 9, 0),
    endAt: dayOffset(3, 11, 0),
    location: "Pete's Garage",
    fanout: true,
    fanoutLabel: "Fanned out to family (car-only event)",
    assignees: [{ kind: "car", id: "c_volvo" }],
    syncStatus: "synced",
    railColor: "stone",
  },
  {
    id: "e_basketball",
    title: "Basketball with friends",
    startAt: dayOffset(3, 14, 0),
    endAt: dayOffset(3, 17, 0),
    location: "Lincoln Rec Center",
    assignees: [{ kind: "member", id: "m_dad" }],
    syncStatus: "synced",
    railColor: "blush",
  },
];

export const MOCK_CHAT: ChatMessage[] = [
  {
    id: "msg_1",
    role: "user",
    authorMemberId: "m_dad",
    content: "What can I make tonight with chicken, rice, and whatever's in the fridge?",
  },
  {
    id: "msg_2",
    role: "ai",
    content: (
      <>
        Looking at the shopping list and recent notes — you&apos;ve got lemons and rosemary on
        hand. How about <b>one-pot lemon rosemary chicken and rice</b>? It&apos;s a 35-minute
        stovetop dish. Want me to walk you through it?
      </>
    ),
    toolCalls: [
      {
        id: "t_1",
        toolName: "list_notes",
        label: "Read notes",
        text: 'Found 2 notes: "shopping-list" and "meal-ideas"',
        status: "done",
      },
    ],
  },
  {
    id: "msg_3",
    role: "user",
    authorMemberId: "m_dad",
    content: 'Sounds good. Also — add "basmati rice" to the shopping list.',
  },
  {
    id: "msg_4",
    role: "ai",
    content: (
      <>
        Done — added <b>basmati rice</b> to the shopping list. Want me to share the full recipe?
      </>
    ),
    toolCalls: [
      {
        id: "t_2",
        toolName: "append_note",
        label: "Update note",
        text: 'Appended "basmati rice" to Shopping list',
        status: "done",
      },
    ],
  },
];

export const MOCK_SUGGESTIONS = [
  "Show me the recipe",
  "What's for dinner this week?",
  "What's on the shopping list?",
  "Plan Ola's birthday party",
];

export const MOCK_PREFS: FamilyPrefs = {
  syncIntervalMinutes: 5,
  fanoutEnabled: true,
  voiceWakeEnabled: false,
  alwaysOn: true,
};

export function getMember(id?: string): Member | undefined {
  return id ? MOCK_MEMBERS.find((m) => m.id === id) : undefined;
}
export function getCar(id?: string): Car | undefined {
  return id ? MOCK_CARS.find((c) => c.id === id) : undefined;
}
