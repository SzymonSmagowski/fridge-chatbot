/**
 * Shared Playwright fixtures: canned API shapes (mirror Architect §5) and a
 * `mockBackend(page)` helper that registers route handlers on the given page.
 *
 * The tests run against the Next.js dev server on port 3000 but intercept
 * every call to the backend (port 8001) — no backend process required.
 * Also stubs `ws://localhost:8001/ws/family/…/events` so the family-events
 * hook doesn't throw a visible error.
 */
import type { Page } from "@playwright/test";

export const API = "http://localhost:8001";

export const FAMILY = {
  id: "fam-1",
  name: "The Magowski Family",
  timezone: "Europe/Warsaw",
  created_at: "2026-01-15T10:00:00Z",
};

export const PREFS = {
  family_id: "fam-1",
  sync_interval_sec: 300,
  fanout_enabled: true,
  voice_wake_enabled: false,
  always_on: true,
  auto_create_shopping_list: true,
  updated_at: "2026-04-24T00:00:00Z",
};

export const MEMBERS = [
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

export const CARS = [
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
];

export const NOTES = [
  {
    id: "n-shopping",
    family_id: "fam-1",
    content: "[ ] milk\n[ ] bread",
    icon: null,
    labels: [{ slug: "shopping-list", display_name: "Shopping list" }],
    pinned: true,
    assignee_member_id: null,
    car_ids: [],
    linked_event_id: null,
    created_at: "2026-04-20T08:00:00Z",
    updated_at: "2026-04-20T08:00:00Z",
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

export const JWT =
  // header.payload with family_id and a user_id claim; no signature check
  // client-side — backend is stubbed, this is decoded only by useFamilyEvents.
  "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." +
  // base64 of {"family_id":"fam-1","sub":"1","exp":9999999999}
  "eyJmYW1pbHlfaWQiOiJmYW0tMSIsInN1YiI6IjEiLCJleHAiOjk5OTk5OTk5OTl9." +
  "x";

export const USER_ME = { id: 1, username: "family", email: null, is_active: true };

/** Call in test.beforeEach to set up deterministic API responses. */
export async function mockBackend(page: Page, overrides: {
  notes?: typeof NOTES;
  members?: typeof MEMBERS;
  cars?: typeof CARS;
  onCreateNote?: (body: unknown) => void;
  onCreateEvent?: (body: unknown) => void;
} = {}) {
  const notes = overrides.notes ?? NOTES;
  const members = overrides.members ?? MEMBERS;
  const cars = overrides.cars ?? CARS;

  await page.route(`${API}/users/me`, (r) =>
    r.fulfill({ json: USER_ME, status: 200 }),
  );
  await page.route(`${API}/family`, (r) => r.fulfill({ json: FAMILY }));
  await page.route(`${API}/family/preferences`, (r) => r.fulfill({ json: PREFS }));

  await page.route(new RegExp(`${API}/members(\\?.*)?$`), (r) =>
    r.fulfill({ json: members }),
  );
  await page.route(new RegExp(`${API}/cars(\\?.*)?$`), (r) =>
    r.fulfill({ json: cars }),
  );

  await page.route(new RegExp(`${API}/notes(\\?.*)?$`), async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      const body = req.postDataJSON() as { content: string; assignee_member_id: string | null };
      overrides.onCreateNote?.(body);
      await route.fulfill({
        status: 201,
        json: {
          id: `n-${Date.now()}`,
          family_id: "fam-1",
          content: body.content,
          icon: null,
          labels: [],
          pinned: false,
          assignee_member_id: body.assignee_member_id ?? null,
          car_ids: [],
          linked_event_id: null,
          created_at: "2026-04-24T12:00:00Z",
          updated_at: "2026-04-24T12:00:00Z",
        },
      });
      return;
    }
    await route.fulfill({ json: { items: notes, total: notes.length } });
  });

  await page.route(new RegExp(`${API}/notes/[^/]+/?$`), async (route) => {
    const req = route.request();
    if (req.method() === "DELETE") return route.fulfill({ status: 204 });
    if (req.method() === "PATCH") {
      const body = req.postDataJSON() as { content?: string };
      return route.fulfill({
        json: { ...notes[0], ...body, updated_at: "2026-04-24T13:00:00Z" },
      });
    }
    return route.fallback();
  });

  await page.route(new RegExp(`${API}/events(\\?.*)?$`), async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      const body = req.postDataJSON() as { title: string };
      overrides.onCreateEvent?.(body);
      return route.fulfill({
        status: 201,
        json: {
          id: `e-${Date.now()}`,
          family_id: "fam-1",
          title: body.title,
          description: null,
          start_at: new Date().toISOString(),
          end_at: new Date(Date.now() + 3_600_000).toISOString(),
          timezone: "Europe/Warsaw",
          location: null,
          assignee_member_id: null,
          car_ids: [],
          rrule: null,
          source: "fridge",
          source_member_id: null,
          targets: [],
          linked_note_id: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });
    }
    return route.fulfill({ json: { items: [], total: 0 } });
  });

  await page.route(`${API}/calendar/sync-state`, (r) => r.fulfill({ json: [] }));
  await page.route(`${API}/threads`, (r) => r.fulfill({ json: [] }));
  await page.route(new RegExp(`${API}/auth/login$`), (r) =>
    r.fulfill({
      json: {
        access_token: JWT,
        token_type: "bearer",
        user: USER_ME,
      },
    }),
  );
}

export async function seedToken(page: Page) {
  await page.addInitScript((token: string) => {
    window.localStorage.setItem("fridge-chatbot-token", token);
    // Pin Paraglide to English so all role/text matchers stay deterministic.
    // Without this, LocaleProvider would seed from navigator.language and
    // a Polish CI runner could flip every assertion.
    window.localStorage.setItem("PARAGLIDE_LOCALE", "en");
  }, JWT);
}

/**
 * Wrap `window.WebSocket` so that connections to the FastAPI events channel
 * (`/ws/family/.../events`) are answered by an in-memory fake that immediately
 * fires `onopen`. Other URLs (Turbopack HMR, Next.js websocket, etc) keep the
 * real implementation — replacing the entire global breaks Next dev mode.
 *
 * Without this wrapper, the family-events hook would fail to connect to a
 * non-existent backend, enter exponential backoff, and after ~9s show a
 * Sonner toast that intercepts pointer events on E2E forms.
 */
export async function stubWebSocket(page: Page) {
  await page.addInitScript(() => {
    const RealWS = window.WebSocket;
    class FakeFamilyWS {
      readyState = 1;
      onopen: ((ev: Event) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      url: string;
      constructor(url: string) {
        this.url = url;
        Promise.resolve().then(() => this.onopen?.(new Event("open")));
      }
      close() {
        this.readyState = 3;
        this.onclose?.(new CloseEvent("close", { code: 1000 }));
      }
      send() {
        /* server-only push channel per Architect §5.11 */
      }
      addEventListener() {}
      removeEventListener() {}
    }
    function WSWrapper(this: unknown, url: string, protocols?: string | string[]) {
      if (url.includes("/ws/family/") && url.includes("/events")) {
        return new FakeFamilyWS(url);
      }
      return new RealWS(url, protocols);
    }
    (WSWrapper as unknown as { CONNECTING: number; OPEN: number; CLOSING: number; CLOSED: number }).CONNECTING = 0;
    (WSWrapper as unknown as { CONNECTING: number; OPEN: number; CLOSING: number; CLOSED: number }).OPEN = 1;
    (WSWrapper as unknown as { CONNECTING: number; OPEN: number; CLOSING: number; CLOSED: number }).CLOSING = 2;
    (WSWrapper as unknown as { CONNECTING: number; OPEN: number; CLOSING: number; CLOSED: number }).CLOSED = 3;
    (window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      WSWrapper as unknown as typeof WebSocket;
  });
}
