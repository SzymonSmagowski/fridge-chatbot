import { http } from "./http";

export interface AuthorizeUrlResponse {
  authorize_url: string;
}

export interface PairingStartResponse {
  authorize_url: string;
  pairing_id: string;
}

/**
 * First-time device pairing — unauth'd. Returns Google consent URL + pairing id.
 * Per Architect §5.0, pairing's REST surface lives under `/api/`.
 */
export const pairingApi = {
  start: (deviceLabel?: string) =>
    http<PairingStartResponse>("/api/pairing/start", {
      method: "POST",
      body: JSON.stringify(deviceLabel ? { device_label: deviceLabel } : {}),
      auth: false,
    }),
};

/**
 * Add-Google flow for an existing member (post-pairing). Per Architect §5.0,
 * the entire `/oauth/*` family stays bare (Google's registered redirect_uri
 * has no `/api/` prefix and rotating it requires consent-screen coordination).
 */
export const oauthApi = {
  authorize: (memberId: string) =>
    http<AuthorizeUrlResponse>(
      `/oauth/google/authorize?member_id=${encodeURIComponent(memberId)}`,
    ),
  revoke: (memberId: string) =>
    http<void>(`/oauth/google/${encodeURIComponent(memberId)}`, {
      method: "DELETE",
    }),
};
