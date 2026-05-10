import { http, jsonBody } from "./http";

/**
 * Categories the user can pick when filing a feedback ticket. Matches the
 * `feedback_category` Postgres enum on the backend (see Architect §B.1).
 */
export type FeedbackCategory = "bug" | "improvement" | "question" | "other";

/**
 * Origin of a feedback row. `user` = filed via REST (settings modal);
 * `assistant_on_behalf_of_user` = the LangGraph `submit_feedback` tool wrote it
 * after the user said yes to the assistant's "want me to log this?" prompt.
 */
export type FeedbackAuthorKind = "user" | "assistant_on_behalf_of_user";

/**
 * Triage state. The backend defaults new rows to `open`; UI consumers don't
 * mutate this — there's no triage UI in scope.
 */
export type FeedbackStatus = "open" | "reviewing" | "resolved";

export interface FeedbackResponse {
  id: string;
  family_id: string;
  member_id: string | null;
  device_id: string | null;
  thread_id: string | null;
  category: FeedbackCategory;
  message: string;
  author_kind: FeedbackAuthorKind;
  status: FeedbackStatus;
  created_at: string;
  updated_at: string;
}

export interface FeedbackListResponse {
  items: FeedbackResponse[];
  total: number;
}

export interface FeedbackCreateRequest {
  category: FeedbackCategory;
  message: string;
  thread_id?: string | null;
}

export interface FeedbackListFilters {
  status?: FeedbackStatus;
  limit?: number;
  offset?: number;
}

function qs(filters: FeedbackListFilters): string {
  const u = new URLSearchParams();
  if (filters.status) u.set("status", filters.status);
  if (filters.limit != null) u.set("limit", String(filters.limit));
  if (filters.offset != null) u.set("offset", String(filters.offset));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const feedbackApi = {
  submit: (body: FeedbackCreateRequest) =>
    http<FeedbackResponse>("/api/feedback", {
      method: "POST",
      body: jsonBody(body),
    }),
  list: (filters: FeedbackListFilters = {}) =>
    http<FeedbackListResponse>(`/api/feedback${qs(filters)}`),
};
