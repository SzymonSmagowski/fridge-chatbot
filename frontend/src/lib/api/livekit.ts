import { http } from "./http";

export interface LiveKitTokenResponse {
  url: string;
  token: string;
  room: string;
  identity: string;
}

export const livekitApi = {
  mintToken: (): Promise<LiveKitTokenResponse> =>
    http<LiveKitTokenResponse>("/api/livekit/token", { method: "POST" }),
};
