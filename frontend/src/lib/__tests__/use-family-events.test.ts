/**
 * Unit tests for the family-events WebSocket hook + reconnect/poll behavior
 * (Architect §5.11 + §7.7).
 *
 * The hook is implemented as a singleton FamilyEventsClient so we test it
 * primarily through `useFamilyEvents` + a mocked WebSocket constructor.
 *
 * NOTE: These tests assert *contract* (close codes, heartbeat ignore, fallback
 * timing). They intentionally don't pin internal timer IDs — that would couple
 * to implementation.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useFamilyEvents } from "@/lib/use-family-events";
import { saveToken, clearToken, getToken } from "@/lib/auth";

interface FakeSocket {
  url: string;
  readyState: number;
  onopen: ((this: WebSocket, ev: Event) => unknown) | null;
  onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null;
  onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null;
  onerror: ((this: WebSocket, ev: Event) => unknown) | null;
  close: (code?: number, reason?: string) => void;
  send: (data: unknown) => void;
  __dispatchOpen: () => void;
  __dispatchMessage: (data: string) => void;
  __dispatchClose: (code: number) => void;
}

const sockets: FakeSocket[] = [];

function FakeWebSocket(this: FakeSocket, url: string): FakeSocket {
  // Track every constructed socket so tests can drive the latest one.
  this.url = url;
  this.readyState = 0;
  this.onopen = null;
  this.onmessage = null;
  this.onclose = null;
  this.onerror = null;
  this.close = (code = 1000) => {
    this.readyState = 3;
    this.onclose?.call(this as unknown as WebSocket, { code } as CloseEvent);
  };
  this.send = () => undefined;
  this.__dispatchOpen = () => {
    this.readyState = 1;
    this.onopen?.call(this as unknown as WebSocket, {} as Event);
  };
  this.__dispatchMessage = (data: string) => {
    this.onmessage?.call(this as unknown as WebSocket, {
      data,
    } as MessageEvent);
  };
  this.__dispatchClose = (code: number) => {
    this.readyState = 3;
    this.onclose?.call(this as unknown as WebSocket, { code } as CloseEvent);
  };
  sockets.push(this);
  return this;
}

// jwt with `family_id: "fam-1"` payload (HS256 sig stripped — hook only decodes payload)
function makeFamilyJwt(familyId = "fam-1"): string {
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" })).replace(/=+$/, "");
  const payload = btoa(JSON.stringify({ family_id: familyId })).replace(/=+$/, "");
  return `${header}.${payload}.sig`;
}

beforeEach(() => {
  sockets.length = 0;
  // Stub global WebSocket — the hook builds `new WebSocket(url)`.
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  saveToken(makeFamilyJwt());
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  clearToken();
});

describe("[unit] useFamilyEvents — websocket lifecycle", () => {
  test("opens a single websocket on first subscriber", () => {
    renderHook(() => useFamilyEvents(() => undefined));
    expect(sockets.length).toBe(1);
    expect(sockets[0].url).toContain("/ws/family/fam-1/events");
    expect(sockets[0].url).toContain("token=");
  });

  test("notifies the listener on a real event frame", () => {
    const cb = vi.fn();
    renderHook(() => useFamilyEvents(cb));
    act(() => sockets[0].__dispatchOpen());
    act(() => sockets[0].__dispatchMessage(JSON.stringify({
      type: "note.created", entity: "notes", id: "n-1", actor: "rest", ts: "2026-04-24T12:00:00Z",
    })));
    expect(cb).toHaveBeenCalledTimes(1);
  });

  test("ignores heartbeat ping frames (no callback fire)", () => {
    const cb = vi.fn();
    renderHook(() => useFamilyEvents(cb));
    act(() => sockets[0].__dispatchOpen());
    // §5.11: clients MUST ignore frames whose `type == "ping"` — feeding them
    // into the callback triggers spurious refetches every 25s.
    //
    // KNOWN BUG (reported to FrontendDeveloper): the production hook only
    // filters frames that are missing `type`; a `{ "type": "ping" }` frame
    // falls through to `notify()` and causes a cache-bust. Once the hook
    // is patched to check `if (payload.type === "ping") return;` this test
    // will keep passing.
    act(() => sockets[0].__dispatchMessage(JSON.stringify({ type: "ping" })));
    expect(cb).not.toHaveBeenCalled();
  });

  test("ignores frames missing a type (tolerates ack/heartbeat shape variants)", () => {
    const cb = vi.fn();
    renderHook(() => useFamilyEvents(cb));
    act(() => sockets[0].__dispatchOpen());
    act(() => sockets[0].__dispatchMessage(JSON.stringify({ entity: "notes" })));
    expect(cb).not.toHaveBeenCalled();
  });

  test("reconnects with backoff after an unexpected close", () => {
    renderHook(() => useFamilyEvents(() => undefined));
    expect(sockets.length).toBe(1);
    // Drop with a generic close code — hook should reconnect after 250ms.
    act(() => sockets[0].__dispatchClose(1006));
    act(() => vi.advanceTimersByTime(260));
    expect(sockets.length).toBe(2);
  });

  test("on close 4003 family_mismatch — clears token and redirects to /pair", () => {
    saveToken(makeFamilyJwt("stale-family"));
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, assign: assignSpy },
    });
    renderHook(() => useFamilyEvents(() => undefined));
    act(() => sockets[0].__dispatchClose(4003));
    expect(getToken()).toBeNull();
    expect(assignSpy).toHaveBeenCalledWith("/pair");
  });

  test("on close 1011 redis_unavailable — waits 10s before reconnecting", () => {
    renderHook(() => useFamilyEvents(() => undefined));
    act(() => sockets[0].__dispatchClose(1011));
    // Backoff schedule's first slot is 250ms — but 1011 must override to 10s.
    act(() => vi.advanceTimersByTime(1000));
    expect(sockets.length).toBe(1);
    act(() => vi.advanceTimersByTime(10_000));
    expect(sockets.length).toBe(2);
  });
});
