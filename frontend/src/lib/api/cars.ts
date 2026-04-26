import { http, jsonBody } from "./http";
import type { MemberColor } from "@/components/fridge/types";

export type CarStatus = "active" | "inactive";

export interface CarResponse {
  id: string;
  family_id: string;
  name: string;
  year: number | null;
  color_label: string | null;
  color: MemberColor;
  notes: string | null;
  status: CarStatus;
  created_at: string;
}

export interface CarCreateRequest {
  name: string;
  year?: number | null;
  color_label?: string | null;
  color: MemberColor;
  notes?: string | null;
}

export type CarUpdateRequest = Partial<CarCreateRequest>;

export type CarStatusFilter = "active" | "inactive" | "all";

export const carsApi = {
  list: (status: CarStatusFilter = "active") =>
    http<CarResponse[]>(`/api/cars?status=${status}`),
  create: (body: CarCreateRequest) =>
    http<CarResponse>("/api/cars", { method: "POST", body: jsonBody(body) }),
  update: (id: string, body: CarUpdateRequest) =>
    http<CarResponse>(`/api/cars/${id}`, {
      method: "PATCH",
      body: jsonBody(body),
    }),
  setActive: (id: string) =>
    http<CarResponse>(`/api/cars/${id}/set-active`, { method: "POST" }),
  setInactive: (id: string) =>
    http<CarResponse>(`/api/cars/${id}/set-inactive`, { method: "POST" }),
  delete: (id: string) =>
    http<void>(`/api/cars/${id}`, { method: "DELETE" }),
};
