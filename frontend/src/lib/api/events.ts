import { http, jsonBody } from "./http";

export type EventSyncStatus = "pending" | "synced" | "failed" | "skipped";

export interface EventTargetView {
  member_id: string;
  google_event_id: string | null;
  sync_status: EventSyncStatus;
  retry_count: number;
  last_error: string | null;
  synced_at: string | null;
}

export type EventSource = "fridge" | "external";

export interface EventResponse {
  id: string;
  family_id: string;
  title: string;
  description: string | null;
  start_at: string;
  end_at: string;
  timezone: string;
  location: string | null;
  assignee_member_id: string | null;
  car_ids: string[];
  rrule: string | null;
  source: EventSource;
  /** Source member id when source=external; null otherwise. */
  source_member_id: string | null;
  targets: EventTargetView[];
  linked_note_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventListResponse {
  items: EventResponse[];
  total: number;
}

export interface EventCreateRequest {
  title: string;
  description?: string | null;
  start_at: string; // ISO
  end_at: string;   // ISO
  timezone?: string;
  location?: string | null;
  assignee_member_id?: string | null;
  car_ids?: string[];
  rrule?: string | null;
  linked_note_id?: string | null;
}

export type EventUpdateRequest = Partial<EventCreateRequest>;

export type EventScope = "instance" | "all_future";

export interface EventListFilters {
  from?: string;
  to?: string;
  member_id?: string;
  car_id?: string;
  source?: EventSource | "all";
}

function qs(filters: EventListFilters): string {
  const u = new URLSearchParams();
  if (filters.from) u.set("from", filters.from);
  if (filters.to) u.set("to", filters.to);
  if (filters.member_id) u.set("member_id", filters.member_id);
  if (filters.car_id) u.set("car_id", filters.car_id);
  if (filters.source) u.set("source", filters.source);
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const eventsApi = {
  list: (filters: EventListFilters = {}) =>
    http<EventListResponse>(`/api/events${qs(filters)}`),
  get: (id: string) => http<EventResponse>(`/api/events/${id}`),
  create: (body: EventCreateRequest) =>
    http<EventResponse>("/api/events", {
      method: "POST",
      body: jsonBody(body),
    }),
  update: (id: string, body: EventUpdateRequest, scope: EventScope = "instance") =>
    http<EventResponse>(`/api/events/${id}?scope=${scope}`, {
      method: "PATCH",
      body: jsonBody(body),
    }),
  delete: (id: string, scope: EventScope = "instance") =>
    http<void>(`/api/events/${id}?scope=${scope}`, { method: "DELETE" }),
  resync: (id: string) =>
    http<EventResponse>(`/api/events/${id}/resync`, { method: "POST" }),
};
