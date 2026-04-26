import { http, jsonBody } from "./http";

export interface NoteLabelView {
  slug: string;
  display_name: string;
}

export interface NoteResponse {
  id: string;
  family_id: string;
  content: string;
  icon: string | null;
  labels: NoteLabelView[];
  pinned: boolean;
  assignee_member_id: string | null;
  car_ids: string[];
  linked_event_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface NoteListResponse {
  items: NoteResponse[];
  total: number;
}

export interface NoteCreateRequest {
  content: string;
  icon?: string | null;
  label_slugs?: string[];
  pinned?: boolean;
  assignee_member_id?: string | null;
  car_ids?: string[];
  linked_event_id?: string | null;
}

export type NoteUpdateRequest = Partial<NoteCreateRequest>;

export interface NoteListFilters {
  pinned?: "true" | "false" | "all";
  label?: string;
  assignee_member_id?: string;
  limit?: number;
  offset?: number;
}

function qs(filters: NoteListFilters): string {
  const u = new URLSearchParams();
  if (filters.pinned) u.set("pinned", filters.pinned);
  if (filters.label) u.set("label", filters.label);
  if (filters.assignee_member_id) u.set("assignee_member_id", filters.assignee_member_id);
  if (filters.limit != null) u.set("limit", String(filters.limit));
  if (filters.offset != null) u.set("offset", String(filters.offset));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const notesApi = {
  list: (filters: NoteListFilters = {}) =>
    http<NoteListResponse>(`/api/notes${qs(filters)}`),
  get: (id: string) => http<NoteResponse>(`/api/notes/${id}`),
  create: (body: NoteCreateRequest) =>
    http<NoteResponse>("/api/notes", {
      method: "POST",
      body: jsonBody(body),
    }),
  update: (id: string, body: NoteUpdateRequest) =>
    http<NoteResponse>(`/api/notes/${id}`, {
      method: "PATCH",
      body: jsonBody(body),
    }),
  delete: (id: string) =>
    http<void>(`/api/notes/${id}`, { method: "DELETE" }),
  appendShoppingList: (line: string) =>
    http<NoteResponse>("/api/notes/shopping-list/append", {
      method: "POST",
      body: jsonBody({ line }),
    }),
};
