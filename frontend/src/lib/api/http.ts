/**
 * Internal HTTP helper used by the per-domain api/* modules.
 *
 * Re-uses the BACKEND_URL + getToken from the existing api.ts module so we
 * stay on a single auth token (the JWT issued by /auth/login today; per
 * Architect §4 the same JWT cookie/localStorage slot will hold the device
 * JWT once /pairing/start is wired through the OAuth flow).
 */
import { getToken } from "@/lib/auth";
import { ApiError, BACKEND_URL } from "./_legacy";
import { toast } from "sonner";
import { m } from "@/paraglide/messages.js";

interface ApiInit extends RequestInit {
  auth?: boolean;
}

interface RateLimitedBody {
  code?: string;
  detail?: string;
  retry_after_sec?: number;
}

let lastRateLimitToastAt = 0;

function maybeToastRateLimit(body: RateLimitedBody) {
  const now = Date.now();
  if (now - lastRateLimitToastAt < 4000) return;
  lastRateLimitToastAt = now;
  const seconds = body.retry_after_sec ?? 60;
  toast.error(
    body.detail ?? m.errors_rate_limit_toast({ seconds }),
  );
}

export async function http<T>(path: string, init: ApiInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (init.auth !== false) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let detail: string | undefined;
    let code: string | undefined;
    let parsedBody: RateLimitedBody | undefined;
    try {
      parsedBody = (await res.json()) as RateLimitedBody;
      detail = parsedBody?.detail;
      code = parsedBody?.code;
    } catch {
      // not JSON
    }

    if (res.status === 429 && parsedBody) {
      maybeToastRateLimit(parsedBody);
    }

    throw new ApiError(
      res.status,
      detail ?? `${res.status} ${res.statusText}`,
      code ?? detail,
    );
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}
