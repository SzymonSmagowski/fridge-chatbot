import { http, jsonBody } from "./http";
import type { MemberColor } from "@/components/fridge/types";

export type MemberStatus = "active" | "inactive";
export type GoogleStatus =
  | "connected"
  | "reconnect_needed"
  | "revoked"
  | "not_connected";

export interface GoogleStateResponse {
  status: GoogleStatus;
  email: string | null;
  connected_at: string | null;
}

export interface MemberResponse {
  id: string;
  family_id: string;
  name: string;
  nickname: string | null;
  color: MemberColor;
  status: MemberStatus;
  is_setup_owner: boolean;
  google: GoogleStateResponse;
  created_at: string;
}

export interface MemberCreateRequest {
  name: string;
  nickname?: string | null;
  color: MemberColor;
}

export type MemberUpdateRequest = Partial<MemberCreateRequest>;

export type MemberStatusFilter = "active" | "inactive" | "all";

export const membersApi = {
  list: (status: MemberStatusFilter = "active") =>
    http<MemberResponse[]>(`/members?status=${status}`),
  get: (id: string) => http<MemberResponse>(`/members/${id}`),
  create: (body: MemberCreateRequest) =>
    http<MemberResponse>("/members", {
      method: "POST",
      body: jsonBody(body),
    }),
  update: (id: string, body: MemberUpdateRequest) =>
    http<MemberResponse>(`/members/${id}`, {
      method: "PATCH",
      body: jsonBody(body),
    }),
  setActive: (id: string) =>
    http<MemberResponse>(`/members/${id}/set-active`, { method: "POST" }),
  setInactive: (id: string) =>
    http<MemberResponse>(`/members/${id}/set-inactive`, { method: "POST" }),
};
