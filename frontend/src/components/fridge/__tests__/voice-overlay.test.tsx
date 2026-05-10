/**
 * Behavioral tests for the voice overlay's close flow.
 *
 * These cover the bug we hit twice in dogfooding: the voice agent (server-
 * side `voice_worker`) calls `session.aclose()` after the LLM uses the
 * `end_session` tool, and the kiosk overlay must dismiss itself in
 * response. We rely on an explicit family-event signal
 * (`voice_session.ended`) over the existing family-events WebSocket
 * because LiveKit's participant-disconnect semantics don't reliably
 * propagate through `useVoiceAssistant().agent === null` in
 * @livekit/components-react@2.9.
 *
 * The tests mock:
 * - `useFamilyEvents` so we can synthetically fire family events
 * - `livekitApi.mintToken` so the overlay reaches the "ready" state
 *   without contacting a real LiveKit server
 * - `VoiceSession` (lazy-loaded) so we don't need a real LiveKit room
 *
 * What we assert:
 * - Overlay does NOT close on unrelated family events
 * - Overlay DOES close on `voice_session.ended`
 * - Overlay does NOT call onClose if it's already closed (open=false)
 */
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";

// --- mocks (must be set up before importing the component under test) ---

// Capture the family-events callback so the test can fire synthetic events.
// We register on mount and unregister on unmount — matches the real
// `useFamilyEvents` hook semantics so React's strict-mode double-mount
// doesn't leave stale listeners.
const familyEventListeners = new Set<
  (event?: { type?: string; entity?: string; id?: string }) => void
>();

vi.mock("@/lib/use-family-events", () => {
  const React = require("react");
  return {
    useFamilyEvents: (
      cb: (event?: { type?: string; entity?: string; id?: string }) => void,
    ) => {
      // Stash latest in a ref so the listener pointer stays stable across
      // renders (mirrors the chat-view pattern); register/unregister once.
      const ref = React.useRef(cb);
      React.useEffect(() => {
        ref.current = cb;
      }, [cb]);
      React.useEffect(() => {
        const handler = (
          event?: { type?: string; entity?: string; id?: string },
        ) => ref.current(event);
        familyEventListeners.add(handler);
        return () => {
          familyEventListeners.delete(handler);
        };
      }, []);
    },
  };
});

// Stub the LiveKit-bearing inner component — we never want to load the real
// SDK in these tests, just verify the overlay's lifecycle around it.
vi.mock("@/components/fridge/voice-session", () => ({
  VoiceSession: () => <div data-testid="voice-session-stub" />,
}));

// Mint-token API call → return a fake credential synchronously.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    livekitApi: {
      mintToken: vi.fn(async () => ({
        url: "ws://example.invalid",
        token: "fake-token",
      })),
    },
  };
});

// `getToken()` must return a non-null value so the overlay doesn't bail to
// the "no-auth" branch. The actual JWT contents aren't validated client-side.
vi.mock("@/lib/auth", () => ({
  getToken: () => "fake-jwt",
}));

// next/dynamic substitute that returns the same VoiceSession stub we mocked
// above, bypassing the lazy-load / SSR machinery the real plugin sets up.
vi.mock("next/dynamic", () => ({
  default: () => () => <div data-testid="voice-session-stub" />,
}));

import { VoiceOverlay } from "@/components/fridge/voice-overlay";

afterEach(() => {
  familyEventListeners.clear();
  vi.clearAllMocks();
});

function fireFamilyEvent(event: { type?: string; entity?: string; id?: string }) {
  // Synthetically dispatch through every listener registered by useFamilyEvents.
  for (const cb of familyEventListeners) cb(event);
}

describe("VoiceOverlay close flow", () => {
  test("voice_session.ended dismisses the overlay", async () => {
    const onClose = vi.fn();
    render(<VoiceOverlay open onClose={onClose} />);

    // Wait for the overlay to register its family-events listener.
    await waitFor(() => expect(familyEventListeners.size).toBeGreaterThan(0));

    act(() => {
      fireFamilyEvent({ type: "voice_session.ended", entity: "voice_session" });
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("unrelated family events do not dismiss the overlay", async () => {
    const onClose = vi.fn();
    render(<VoiceOverlay open onClose={onClose} />);
    await waitFor(() => expect(familyEventListeners.size).toBeGreaterThan(0));

    act(() => {
      fireFamilyEvent({ type: "note.created", entity: "notes" });
      fireFamilyEvent({ type: "thread_message.created", entity: "messages" });
      fireFamilyEvent({ type: "family_preferences.updated" });
    });

    expect(onClose).not.toHaveBeenCalled();
  });

  test("voice_session.ended is ignored when overlay is already closed", async () => {
    const onClose = vi.fn();
    render(<VoiceOverlay open={false} onClose={onClose} />);
    await waitFor(() => expect(familyEventListeners.size).toBeGreaterThan(0));

    act(() => {
      fireFamilyEvent({ type: "voice_session.ended", entity: "voice_session" });
    });

    // No close because we're already closed — preventing double-fire on
    // events that arrive while the overlay isn't mounted-visible.
    expect(onClose).not.toHaveBeenCalled();
  });

  test("renders nothing when open=false", () => {
    render(<VoiceOverlay open={false} onClose={() => undefined} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
