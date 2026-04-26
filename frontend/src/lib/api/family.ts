import { http, jsonBody } from "./http";

export interface FamilyResponse {
  id: string;
  name: string;
  timezone: string;
  created_at: string;
}

export interface FamilyUpdateRequest {
  name?: string;
  timezone?: string;
}

export interface FamilyPreferencesResponse {
  family_id: string;
  sync_interval_sec: number;
  fanout_enabled: boolean;
  voice_wake_enabled: boolean;
  always_on: boolean;
  auto_create_shopping_list: boolean;
  updated_at: string;
}

export type FamilyPreferencesPatch = Partial<
  Omit<FamilyPreferencesResponse, "family_id" | "updated_at">
>;

export const familyApi = {
  get: () => http<FamilyResponse>("/api/family"),
  patch: (body: FamilyUpdateRequest) =>
    http<FamilyResponse>("/api/family", {
      method: "PATCH",
      body: jsonBody(body),
    }),
  getPreferences: () =>
    http<FamilyPreferencesResponse>("/api/family/preferences"),
  patchPreferences: (body: FamilyPreferencesPatch) =>
    http<FamilyPreferencesResponse>("/api/family/preferences", {
      method: "PATCH",
      body: jsonBody(body),
    }),
};
