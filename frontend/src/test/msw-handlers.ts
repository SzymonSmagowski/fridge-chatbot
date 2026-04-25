/**
 * Canned MSW handlers for Architect §5 endpoints.
 *
 * These shapes mirror the contract verbatim so tests catch the case where
 * production code drifts from the Architect's spec. Update only when §5
 * itself changes — and flag drift to BackendTester so contract tests stay
 * in sync.
 */
import { http, HttpResponse } from "msw";
import type {
  CarResponse,
  EventListResponse,
  EventResponse,
  FamilyPreferencesResponse,
  FamilyResponse,
  MemberResponse,
  NoteListResponse,
  NoteResponse,
  SyncStateResponse,
} from "@/lib/api";

const BACKEND = "http://localhost:8001";

export const FIXTURE_FAMILY: FamilyResponse = {
  id: "fam-1",
  name: "The Magowski Family",
  timezone: "Europe/Warsaw",
  created_at: "2026-01-15T10:00:00Z",
};

export const FIXTURE_PREFERENCES: FamilyPreferencesResponse = {
  family_id: "fam-1",
  sync_interval_sec: 300,
  fanout_enabled: true,
  voice_wake_enabled: false,
  always_on: true,
  auto_create_shopping_list: true,
  updated_at: "2026-04-20T09:00:00Z",
};

export const FIXTURE_MEMBERS: MemberResponse[] = [
  {
    id: "m-mom",
    family_id: "fam-1",
    name: "Monika",
    nickname: "Mom",
    color: "blush",
    status: "active",
    is_setup_owner: false,
    google: { status: "connected", email: "monika@gmail.com", connected_at: "2026-04-01T08:00:00Z" },
    created_at: "2026-04-01T08:00:00Z",
  },
  {
    id: "m-dad",
    family_id: "fam-1",
    name: "Szymon",
    nickname: "Dad",
    color: "blue",
    status: "active",
    is_setup_owner: true,
    google: { status: "connected", email: "szymon@gmail.com", connected_at: "2026-04-01T08:05:00Z" },
    created_at: "2026-04-01T08:05:00Z",
  },
  {
    id: "m-ola",
    family_id: "fam-1",
    name: "Ola",
    nickname: null,
    color: "sage",
    status: "active",
    is_setup_owner: false,
    google: { status: "not_connected", email: null, connected_at: null },
    created_at: "2026-04-02T09:00:00Z",
  },
];

export const FIXTURE_CARS: CarResponse[] = [
  {
    id: "c-volvo",
    family_id: "fam-1",
    name: "Family Volvo",
    year: 2019,
    color_label: "White",
    color: "stone",
    notes: null,
    status: "active",
    created_at: "2026-04-02T09:30:00Z",
  },
  {
    id: "c-civic",
    family_id: "fam-1",
    name: "Red Civic",
    year: 2015,
    color_label: "Red",
    color: "blush",
    notes: null,
    status: "active",
    created_at: "2026-04-02T09:35:00Z",
  },
];

export const FIXTURE_NOTES: NoteResponse[] = [
  {
    id: "n-shopping",
    family_id: "fam-1",
    content: "[ ] milk\n[ ] bread\n[x] coffee",
    icon: null,
    labels: [{ slug: "shopping-list", display_name: "Shopping list" }],
    pinned: true,
    assignee_member_id: null,
    car_ids: [],
    linked_event_id: null,
    created_at: "2026-04-20T08:00:00Z",
    updated_at: "2026-04-20T08:30:00Z",
  },
  {
    id: "n-trash",
    family_id: "fam-1",
    content: "Take out trash Mon 8am",
    icon: "trash",
    labels: [{ slug: "reminder", display_name: "Reminder" }],
    pinned: true,
    assignee_member_id: "m-dad",
    car_ids: [],
    linked_event_id: null,
    created_at: "2026-04-19T18:00:00Z",
    updated_at: "2026-04-19T18:00:00Z",
  },
  {
    id: "n-dentist",
    family_id: "fam-1",
    content: "Dentist appt for Ola\nThursday 3pm",
    icon: null,
    labels: [],
    pinned: false,
    assignee_member_id: "m-ola",
    car_ids: [],
    linked_event_id: null,
    created_at: "2026-04-22T10:00:00Z",
    updated_at: "2026-04-22T10:00:00Z",
  },
];

export const FIXTURE_EVENTS: EventResponse[] = [
  {
    id: "e-soccer",
    family_id: "fam-1",
    title: "Soccer practice",
    description: null,
    start_at: "2026-04-22T16:00:00Z",
    end_at: "2026-04-22T17:30:00Z",
    timezone: "Europe/Warsaw",
    location: "Riverside Park",
    assignee_member_id: "m-ola",
    car_ids: [],
    rrule: null,
    source: "fridge",
    source_member_id: null,
    targets: [
      {
        member_id: "m-ola",
        google_event_id: "g-soccer",
        sync_status: "synced",
        retry_count: 0,
        last_error: null,
        synced_at: "2026-04-22T15:00:00Z",
      },
    ],
    linked_note_id: null,
    created_at: "2026-04-20T10:00:00Z",
    updated_at: "2026-04-20T10:00:00Z",
  },
];

export const FIXTURE_SYNC_STATES: SyncStateResponse[] = [
  {
    member_id: "m-mom",
    last_pull_at: "2026-04-24T11:58:00Z",
    last_error: null,
    last_error_at: null,
    consecutive_failures: 0,
    status: "healthy",
  },
  {
    member_id: "m-dad",
    last_pull_at: "2026-04-24T11:56:00Z",
    last_error: null,
    last_error_at: null,
    consecutive_failures: 0,
    status: "healthy",
  },
];

/** Default success-path handlers — tests can `server.use(...)` to override. */
export function successHandlers(opts?: {
  notes?: NoteResponse[];
  members?: MemberResponse[];
  cars?: CarResponse[];
  events?: EventResponse[];
}) {
  const notes = opts?.notes ?? FIXTURE_NOTES;
  const members = opts?.members ?? FIXTURE_MEMBERS;
  const cars = opts?.cars ?? FIXTURE_CARS;
  const events = opts?.events ?? FIXTURE_EVENTS;

  return [
    http.get(`${BACKEND}/family`, () => HttpResponse.json(FIXTURE_FAMILY)),
    http.get(`${BACKEND}/family/preferences`, () =>
      HttpResponse.json(FIXTURE_PREFERENCES),
    ),
    http.patch(`${BACKEND}/family/preferences`, async ({ request }) => {
      const body = (await request.json()) as Partial<FamilyPreferencesResponse>;
      return HttpResponse.json({ ...FIXTURE_PREFERENCES, ...body });
    }),

    http.get(`${BACKEND}/members`, ({ request }) => {
      const url = new URL(request.url);
      const status = url.searchParams.get("status") ?? "active";
      const filtered =
        status === "all" ? members : members.filter((m) => m.status === status);
      return HttpResponse.json(filtered);
    }),
    http.post(`${BACKEND}/members`, async ({ request }) => {
      const body = (await request.json()) as {
        name: string;
        nickname?: string | null;
        color: MemberResponse["color"];
      };
      const created: MemberResponse = {
        id: `m-${body.name.toLowerCase()}`,
        family_id: "fam-1",
        name: body.name,
        nickname: body.nickname ?? null,
        color: body.color,
        status: "active",
        is_setup_owner: false,
        google: { status: "not_connected", email: null, connected_at: null },
        created_at: new Date().toISOString(),
      };
      return HttpResponse.json(created, { status: 201 });
    }),
    http.post(`${BACKEND}/members/:id/set-inactive`, ({ params }) => {
      const m = members.find((x) => x.id === params.id);
      if (!m)
        return HttpResponse.json(
          { detail: "Not found", code: "members.not_found" },
          { status: 404 },
        );
      return HttpResponse.json({ ...m, status: "inactive" as const });
    }),

    http.get(`${BACKEND}/cars`, ({ request }) => {
      const url = new URL(request.url);
      const status = url.searchParams.get("status") ?? "active";
      const filtered =
        status === "all" ? cars : cars.filter((c) => c.status === status);
      return HttpResponse.json(filtered);
    }),
    http.post(`${BACKEND}/cars`, async ({ request }) => {
      const body = (await request.json()) as {
        name: string;
        year?: number | null;
        color: CarResponse["color"];
        color_label?: string | null;
        notes?: string | null;
      };
      const created: CarResponse = {
        id: `c-${body.name.toLowerCase().replace(/\s+/g, "-")}`,
        family_id: "fam-1",
        name: body.name,
        year: body.year ?? null,
        color_label: body.color_label ?? null,
        color: body.color,
        notes: body.notes ?? null,
        status: "active",
        created_at: new Date().toISOString(),
      };
      return HttpResponse.json(created, { status: 201 });
    }),
    http.delete(`${BACKEND}/cars/:id`, () => new HttpResponse(null, { status: 204 })),

    http.get(`${BACKEND}/notes`, () =>
      HttpResponse.json<NoteListResponse>({ items: notes, total: notes.length }),
    ),
    http.post(`${BACKEND}/notes`, async ({ request }) => {
      const body = (await request.json()) as {
        content: string;
        assignee_member_id?: string | null;
      };
      const created: NoteResponse = {
        id: `n-${Date.now()}`,
        family_id: "fam-1",
        content: body.content,
        icon: null,
        labels: [],
        pinned: false,
        assignee_member_id: body.assignee_member_id ?? null,
        car_ids: [],
        linked_event_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(`${BACKEND}/notes/:id`, async ({ params, request }) => {
      const target = notes.find((n) => n.id === params.id);
      if (!target)
        return HttpResponse.json(
          { detail: "Not found", code: "notes.not_found" },
          { status: 404 },
        );
      const body = (await request.json()) as Partial<NoteResponse>;
      return HttpResponse.json({ ...target, ...body, updated_at: new Date().toISOString() });
    }),
    http.delete(`${BACKEND}/notes/:id`, () => new HttpResponse(null, { status: 204 })),

    http.get(`${BACKEND}/events`, () =>
      HttpResponse.json<EventListResponse>({ items: events, total: events.length }),
    ),
    http.post(`${BACKEND}/events`, async ({ request }) => {
      const body = (await request.json()) as Partial<EventResponse> & { title: string };
      const created: EventResponse = {
        id: `e-${Date.now()}`,
        family_id: "fam-1",
        title: body.title,
        description: body.description ?? null,
        start_at: body.start_at ?? new Date().toISOString(),
        end_at: body.end_at ?? new Date(Date.now() + 3_600_000).toISOString(),
        timezone: "Europe/Warsaw",
        location: body.location ?? null,
        assignee_member_id: body.assignee_member_id ?? null,
        car_ids: body.car_ids ?? [],
        rrule: body.rrule ?? null,
        source: "fridge",
        source_member_id: null,
        targets: [],
        linked_note_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      return HttpResponse.json(created, { status: 201 });
    }),

    http.get(`${BACKEND}/calendar/sync-state`, () =>
      HttpResponse.json(FIXTURE_SYNC_STATES),
    ),
  ];
}

export const handlers = successHandlers();
