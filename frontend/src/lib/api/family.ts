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

/**
 * Household default language for the assistants. `auto` (default) → the
 * detect_language graph node runs per-turn detection from user input.
 * `en`/`pl` → seed default; per-turn detection still overrides on clear
 * opposite-language input. Drives the voice agent's greeting too.
 */
export type VoiceLocale = "auto" | "en" | "pl";

export interface FamilyPreferencesResponse {
  family_id: string;
  sync_interval_sec: number;
  fanout_enabled: boolean;
  voice_wake_enabled: boolean;
  always_on: boolean;
  auto_create_shopping_list: boolean;
  voice_locale: VoiceLocale;
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
