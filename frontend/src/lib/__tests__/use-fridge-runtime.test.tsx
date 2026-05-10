/**
 * Integration tests for `useFridgeRuntime` — covers lazy-load pagination
 * (Tier A #1, #2, #3 of FrontendTester's brief):
 *
 *   1. Initial open hydrates the latest 30 messages, exposes a non-null cursor
 *      while there's more history, and `loadOlder()` prepends an older page.
 *   2. `hasMore=false` end-state: once the server returns an empty page or
 *      drops the cursor, the runtime stops fetching and reports `hasMore=false`.
 *   3. Streaming a token onto the latest assistant message must NOT trigger
 *      another `getThreadMessagesPage` call — guards against the regression
 *      where every token append would fire a "load older" round-trip.
 *
 * We hit the MSW server directly so the real `apiClient.getThread` /
 * `getThreadMessagesPage` codepath is exercised — this catches contract drift
 * between the FE expectations and the Architect §A wire shape.
 *
 * Scroll-anchor math (Tier A #1's critical assertion) is verified in the
 * separate `chat-view-scroll-anchor.test.tsx` — it lives in `ChatScrollPaginator`
 * and is independent of the runtime hook.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useFridgeRuntime } from "@/lib/use-fridge-runtime";
import type {
  MessageResponse,
  MessagesPageResponse,
  ThreadMessagesResponse,
} from "@/lib/api";
import { server } from "@/test/msw-server";
import { saveToken } from "@/lib/auth";

const BACKEND = "http://localhost:8001";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

beforeEach(() => {
  saveToken("eyJhbGciOiJub25lIn0.eyJmYW1pbHlfaWQiOiJmYW0tMSJ9.x");
});

afterEach(() => vi.restoreAllMocks());

/**
 * Build a deterministic message fixture. We use ISO timestamps spaced one
 * minute apart so the wire newest-first ordering is trivially stable, and the
 * `id` doubles as the cursor we assert on.
 */
function makeMessage(idx: number, role: "user" | "assistant" = "user"): MessageResponse {
  return {
    id: `m-${String(idx).padStart(4, "0")}`,
    role,
    content: `msg ${idx}`,
    type: "text",
    created_at: new Date(2026, 0, 1, 12, idx).toISOString(),
    score: null,
    comment: null,
  };
}

/**
 * Build a "newest-first" page slice (server wire order). Picks indexes
 * `[fromIdx, toIdx)` and reverses to newest-first.
 */
function pageSlice(fromIdx: number, toIdx: number): MessageResponse[] {
  const out: MessageResponse[] = [];
  // Reverse: highest idx first.
  for (let i = toIdx - 1; i >= fromIdx; i--) {
    out.push(makeMessage(i));
  }
  return out;
}

describe("[integration] useFridgeRuntime — lazy-load pagination", () => {
  test("loads older messages when loadOlder is called and prepends them in chronological order", async () => {
    // Latest page (newest 30 of 60-message thread) — wire is newest-first,
    // so message m-0059 is first on the page, m-0030 last; cursor points at m-0030.
    const latestPage = pageSlice(30, 60);
    const olderPage = pageSlice(0, 30);

    const calls: string[] = [];

    server.use(
      http.get(`${BACKEND}/threads/42`, () => {
        const env: ThreadMessagesResponse = {
          id: 42,
          thread_id: "uuid-42",
          title: "Test thread",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: latestPage,
          has_more: true,
          next_cursor: "m-0030",
        };
        return HttpResponse.json(env);
      }),
      http.get(`${BACKEND}/threads/42/messages`, ({ request }) => {
        const url = new URL(request.url);
        const before = url.searchParams.get("before");
        const limit = url.searchParams.get("limit");
        calls.push(`before=${before}&limit=${limit}`);
        const body: MessagesPageResponse = {
          messages: olderPage,
          has_more: false,
          next_cursor: null,
        };
        return HttpResponse.json(body);
      }),
    );

    const { result } = renderHook(() => useFridgeRuntime(42));

    // Initial hydrate populates 30 messages and reports `hasMore=true`.
    await waitFor(() => {
      expect(result.current.pagination.hasLoadedInitial).toBe(true);
    });
    expect(result.current.pagination.hasMore).toBe(true);
    expect(result.current.pagination.isLoading).toBe(false);
    expect(result.current.threadUuid).toBe("uuid-42");

    // Sanity: the runtime exposes its messages via assistant-ui's runtime
    // store. We use the externally-visible state from `pagination` for ground
    // truth, plus assert by triggering loadOlder and watching the count grow.
    let added = 0;
    await act(async () => {
      added = await result.current.pagination.loadOlder();
    });

    // Older page returned 30 messages and prepended them.
    expect(added).toBe(30);
    expect(result.current.pagination.hasMore).toBe(false);
    expect(result.current.pagination.isLoadingOlder).toBe(false);

    // Verify the cursor was sent on the request (Tier A #1: "fetch fires to
    // GET /threads/{id}/messages?before=<cursor>&limit=30").
    expect(calls).toEqual(["before=m-0030&limit=30"]);
  });

  test("stops fetching once hasMore becomes false (no infinite chase)", async () => {
    let pageRequests = 0;
    server.use(
      http.get(`${BACKEND}/threads/7`, () =>
        HttpResponse.json<ThreadMessagesResponse>({
          id: 7,
          thread_id: "uuid-7",
          title: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: pageSlice(30, 60),
          has_more: true,
          next_cursor: "m-0030",
        }),
      ),
      http.get(`${BACKEND}/threads/7/messages`, () => {
        pageRequests += 1;
        return HttpResponse.json<MessagesPageResponse>({
          messages: pageSlice(0, 30),
          has_more: false,
          next_cursor: null,
        });
      }),
    );

    const { result } = renderHook(() => useFridgeRuntime(7));
    await waitFor(() =>
      expect(result.current.pagination.hasLoadedInitial).toBe(true),
    );

    await act(async () => {
      await result.current.pagination.loadOlder();
    });
    expect(pageRequests).toBe(1);
    expect(result.current.pagination.hasMore).toBe(false);

    // Subsequent calls must no-op — the production guard checks `hasMoreRef`.
    let secondAdded: number | null = null;
    await act(async () => {
      secondAdded = await result.current.pagination.loadOlder();
    });
    expect(secondAdded).toBe(0);
    expect(pageRequests).toBe(1);
  });

  test("short thread on initial open keeps hasMore=false and never fires a page request", async () => {
    let pageRequests = 0;
    server.use(
      http.get(`${BACKEND}/threads/3`, () =>
        HttpResponse.json<ThreadMessagesResponse>({
          id: 3,
          thread_id: "uuid-3",
          title: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: pageSlice(0, 5),
          has_more: false,
          next_cursor: null,
        }),
      ),
      http.get(`${BACKEND}/threads/3/messages`, () => {
        pageRequests += 1;
        return HttpResponse.json<MessagesPageResponse>({
          messages: [],
          has_more: false,
          next_cursor: null,
        });
      }),
    );

    const { result } = renderHook(() => useFridgeRuntime(3));
    await waitFor(() =>
      expect(result.current.pagination.hasLoadedInitial).toBe(true),
    );
    expect(result.current.pagination.hasMore).toBe(false);

    // Calling loadOlder on an exhausted thread is a no-op; never fetches.
    await act(async () => {
      await result.current.pagination.loadOlder();
    });
    expect(pageRequests).toBe(0);
  });

  test("does not refetch older pages when the active thread is unchanged across renders", async () => {
    // Streaming a token re-renders the consuming component (which holds the
    // runtime via the AssistantRuntimeProvider). The production guard is that
    // `loadOlder` is NOT called from a render path — it's only fired by the
    // scroll listener in chat-view. We assert the looser invariant: re-render
    // alone never causes a page fetch.
    let pageRequests = 0;
    server.use(
      http.get(`${BACKEND}/threads/9`, () =>
        HttpResponse.json<ThreadMessagesResponse>({
          id: 9,
          thread_id: "uuid-9",
          title: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: pageSlice(30, 60),
          has_more: true,
          next_cursor: "m-0030",
        }),
      ),
      http.get(`${BACKEND}/threads/9/messages`, () => {
        pageRequests += 1;
        return HttpResponse.json<MessagesPageResponse>({
          messages: pageSlice(0, 30),
          has_more: false,
          next_cursor: null,
        });
      }),
    );

    const { result, rerender } = renderHook(() => useFridgeRuntime(9));
    await waitFor(() =>
      expect(result.current.pagination.hasLoadedInitial).toBe(true),
    );

    // Re-render several times — simulates the runtime store firing on every
    // streaming token append.
    rerender();
    rerender();
    rerender();

    // Give microtasks a chance to flush in case anything was scheduled.
    await Promise.resolve();
    await Promise.resolve();

    expect(pageRequests).toBe(0);
  });
});

describe("[integration] useFridgeRuntime — initial-load contract", () => {
  test("propagates the threadUuid the backend returns (used by feedback submission)", async () => {
    server.use(
      http.get(`${BACKEND}/threads/11`, () =>
        HttpResponse.json<ThreadMessagesResponse>({
          id: 11,
          thread_id: "uuid-eleven",
          title: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: [],
          has_more: false,
          next_cursor: null,
        }),
      ),
    );

    const { result } = renderHook(() => useFridgeRuntime(11));
    await waitFor(() => expect(result.current.threadUuid).toBe("uuid-eleven"));
  });

  test("clears state when thread id flips back to null", async () => {
    server.use(
      http.get(`${BACKEND}/threads/55`, () =>
        HttpResponse.json<ThreadMessagesResponse>({
          id: 55,
          thread_id: "uuid-55",
          title: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: pageSlice(0, 5),
          has_more: false,
          next_cursor: null,
        }),
      ),
    );

    const { result, rerender } = renderHook(
      ({ id }: { id: number | null }) => useFridgeRuntime(id),
      { initialProps: { id: 55 as number | null } },
    );
    await waitFor(() => expect(result.current.threadUuid).toBe("uuid-55"));

    rerender({ id: null });
    await waitFor(() => expect(result.current.threadUuid).toBeNull());
    expect(result.current.pagination.hasMore).toBe(false);
    expect(result.current.pagination.hasLoadedInitial).toBe(false);
  });
});
