import { http } from "./http";

export interface AuthorizeUrlResponse {
  authorize_url: string;
}

export interface PairingStartResponse {
  authorize_url: string;
  pairing_id: string;
}

/** First-time device pairing — unauth'd. Returns Google consent URL + pairing id. */
export const pairingApi = {
  start: (deviceLabel?: string) =>
    http<PairingStartResponse>("/pairing/start", {
      method: "POST",
      body: JSON.stringify(deviceLabel ? { device_label: deviceLabel } : {}),
      auth: false,
    }),
};

/** Add-Google flow for an existing member (post-pairing). */
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
