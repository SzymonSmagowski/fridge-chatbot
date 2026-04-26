import { http } from "./http";

export interface SyncStateResponse {
  member_id: string;
  last_pull_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  consecutive_failures: number;
  status: "healthy" | "warning" | "failing";
}

export const calendarSyncApi = {
  state: () => http<SyncStateResponse[]>("/api/calendar/sync-state"),
  pullMember: (memberId: string) =>
    http<SyncStateResponse>(
      `/api/calendar/sync/pull?member_id=${encodeURIComponent(memberId)}`,
      { method: "POST" },
    ),
};
