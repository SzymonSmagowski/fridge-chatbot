"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import { BACKEND_URL } from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";

/**
 * Subscribe to family-wide board mutations (notes/events/cars/members/labels/
 * family/family_preferences).
 *
 * Per Architect §7.7 the backend publishes to Redis channel
 * `family:{family_id}:events`; FastAPI exposes `WS /ws/family/{family_id}/events`
 * which tails that channel for one connected client. This hook opens that
 * WebSocket once per process (shared across all subscribers), fans events to
 * every `onChange` callback, and auto-reconnects with exponential backoff.
 *
 * If the WS stays disconnected for more than `POLL_FALLBACK_AFTER_MS`, it
 * resumes the legacy poll-on-focus behavior so the UI is still eventually
 * consistent while the backend recovers. When the WS reconnects, it switches
 * back to push mode.
 *
 * The hook signature is unchanged from the polling version so existing call
 * sites (`app-shell.tsx`, `notes-view.tsx`, `calendar-view.tsx`) need no edits.
 */

const POLL_INTERVAL_MS = 30_000;
const POLL_FALLBACK_AFTER_MS = 10_000;

const BACKOFF_SCHEDULE_MS = [250, 500, 1000, 2000, 5000] as const;
const BACKEND_ERROR_RETRY_MS = 10_000;
const RECONNECT_TOAST_AFTER_ATTEMPTS = 5;
const RECONNECT_TOAST_ID = "family-events-reconnect";

const WS_CLOSE_FAMILY_MISMATCH = 4003;
const WS_CLOSE_INTERNAL_ERROR = 1011;

export interface FamilyEventPayload {
  type?: string;
  entity?: string;
  id?: string;
  actor?: string;
  ts?: string;
}

type Listener = (payload?: FamilyEventPayload) => void;

/**
 * Decode the `family_id` claim from a JWT without verifying the signature.
 * The backend re-validates on connect; this is purely to build the URL.
 */
function readFamilyIdFromToken(token: string): string | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const json = JSON.parse(atob(padded)) as { family_id?: unknown };
    return typeof json.family_id === "string" ? json.family_id : null;
  } catch {
    return null;
  }
}

function buildWsUrl(familyId: string, token: string): string {
  const url = new URL(`/ws/family/${familyId}/events`, BACKEND_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", token);
  return url.toString();
}

class FamilyEventsClient {
  private listeners = new Set<Listener>();
  private ws: WebSocket | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private pollInterval: number | null = null;
  private pollStartTimer: number | null = null;
  private focusHandler: (() => void) | null = null;
  private visibilityHandler: (() => void) | null = null;
  private pollActive = false;
  private reconnectToastShown = false;
  private connected = false;

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    if (this.listeners.size === 1) {
      this.start();
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        this.stop();
      }
    };
  }

  private notify(payload?: FamilyEventPayload): void {
    for (const listener of this.listeners) {
      try {
        listener(payload);
      } catch (err) {
        console.error("[family-events] listener threw", err);
      }
    }
  }

  private start(): void {
    if (typeof window === "undefined") return;
    this.reconnectAttempt = 0;
    this.schedulePollFallback();
    this.connect();
  }

  private stop(): void {
    this.clearReconnectTimer();
    this.clearPollFallbackTimer();
    this.stopPolling();
    this.dismissReconnectToast();
    this.connected = false;

    const ws = this.ws;
    this.ws = null;
    if (ws) {
      // Strip listeners so the close doesn't retrigger reconnection.
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      try {
        ws.close(1000, "unmount");
      } catch {
        // ignore
      }
    }
  }

  private connect(): void {
    if (typeof window === "undefined") return;
    if (this.ws) return;

    const token = getToken();
    if (!token) {
      // No token yet — retry on the next tick of the backoff schedule. The
      // user is likely still on the login / pairing screen; once auth lands
      // the next reconnect attempt will succeed.
      this.scheduleReconnect();
      return;
    }

    const familyId = readFamilyIdFromToken(token);
    if (!familyId) {
      // Legacy user-JWT without family_id claim. Stay on polling fallback —
      // don't spam reconnects.
      this.startPolling();
      return;
    }

    let ws: WebSocket;
    try {
      ws = new WebSocket(buildWsUrl(familyId, token));
    } catch (err) {
      console.warn("[family-events] WebSocket construction failed", err);
      this.scheduleReconnect();
      return;
    }

    this.ws = ws;

    ws.onopen = () => {
      this.connected = true;
      this.reconnectAttempt = 0;
      this.clearPollFallbackTimer();
      this.stopPolling();
      this.dismissReconnectToast();
      this.schedulePollFallback();
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      let payload: FamilyEventPayload;
      try {
        payload = JSON.parse(ev.data) as FamilyEventPayload;
      } catch {
        return;
      }
      // Heartbeat frames per architecture §5.11 — ignore. Also tolerate any
      // frame missing `type` as a safety net.
      if (!payload.type || payload.type === "ping") return;
      this.notify(payload);
    };

    ws.onerror = () => {
      // Let `onclose` drive reconnect; onerror fires before close in browsers.
    };

    ws.onclose = (ev) => {
      this.connected = false;
      this.ws = null;

      if (ev.code === WS_CLOSE_FAMILY_MISMATCH) {
        // Device JWT's family_id no longer matches — token is stale/revoked.
        // Drop the token and send the user back to the pairing flow.
        clearToken();
        if (typeof window !== "undefined") {
          window.location.assign("/pair");
        }
        return;
      }

      if (ev.code === WS_CLOSE_INTERNAL_ERROR) {
        this.scheduleReconnect(BACKEND_ERROR_RETRY_MS);
        return;
      }

      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(overrideMs?: number): void {
    this.clearReconnectTimer();
    const delay =
      overrideMs ??
      BACKOFF_SCHEDULE_MS[
        Math.min(this.reconnectAttempt, BACKOFF_SCHEDULE_MS.length - 1)
      ];
    this.reconnectAttempt += 1;
    console.info(
      `[family-events] reconnect in ${delay}ms (attempt ${this.reconnectAttempt})`,
    );
    if (this.reconnectAttempt === RECONNECT_TOAST_AFTER_ATTEMPTS) {
      this.showReconnectToast();
    }
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private schedulePollFallback(): void {
    this.clearPollFallbackTimer();
    this.pollStartTimer = window.setTimeout(() => {
      this.pollStartTimer = null;
      if (!this.connected) this.startPolling();
    }, POLL_FALLBACK_AFTER_MS);
  }

  private clearPollFallbackTimer(): void {
    if (this.pollStartTimer !== null) {
      window.clearTimeout(this.pollStartTimer);
      this.pollStartTimer = null;
    }
  }

  private startPolling(): void {
    if (this.pollActive || typeof window === "undefined") return;
    this.pollActive = true;
    console.info("[family-events] WS offline — polling fallback active");

    this.notify();
    this.pollInterval = window.setInterval(() => this.notify(), POLL_INTERVAL_MS);

    const onFocus = () => this.notify();
    const onVisibility = () => {
      if (document.visibilityState === "visible") this.notify();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    this.focusHandler = onFocus;
    this.visibilityHandler = onVisibility;
  }

  private stopPolling(): void {
    if (!this.pollActive) return;
    this.pollActive = false;
    if (this.pollInterval !== null) {
      window.clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    if (this.focusHandler) {
      window.removeEventListener("focus", this.focusHandler);
      this.focusHandler = null;
    }
    if (this.visibilityHandler) {
      document.removeEventListener("visibilitychange", this.visibilityHandler);
      this.visibilityHandler = null;
    }
  }

  private showReconnectToast(): void {
    if (this.reconnectToastShown) return;
    this.reconnectToastShown = true;
    toast.warning("Reconnecting to family updates…", {
      id: RECONNECT_TOAST_ID,
      duration: Infinity,
    });
  }

  private dismissReconnectToast(): void {
    if (!this.reconnectToastShown) return;
    this.reconnectToastShown = false;
    toast.dismiss(RECONNECT_TOAST_ID);
  }
}

const client = new FamilyEventsClient();

export function useFamilyEvents(
  onChange: (payload?: FamilyEventPayload) => void,
): void {
  useEffect(() => {
    return client.subscribe(onChange);
  }, [onChange]);
}
