import { http, jsonBody } from "./http";

export interface LabelResponse {
  slug: string;
  display_name: string;
  is_reserved: boolean;
  note_count: number;
}

export interface LabelCreateRequest {
  slug: string;
  display_name: string;
}

export interface LabelUpdateRequest {
  display_name: string;
}

export const labelsApi = {
  list: () => http<LabelResponse[]>("/api/labels"),
  create: (body: LabelCreateRequest) =>
    http<LabelResponse>("/api/labels", {
      method: "POST",
      body: jsonBody(body),
    }),
  update: (slug: string, body: LabelUpdateRequest) =>
    http<LabelResponse>(`/api/labels/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      body: jsonBody(body),
    }),
  delete: (slug: string) =>
    http<void>(`/api/labels/${encodeURIComponent(slug)}`, { method: "DELETE" }),
};

export const SHOPPING_LIST_SLUG = "shopping-list";
