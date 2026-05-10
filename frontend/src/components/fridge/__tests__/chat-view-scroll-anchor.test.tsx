/**
 * Component test for ChatView's scroll-anchor restoration after a lazy
 * `loadOlder` page is prepended (Tier A #1's critical assertion).
 *
 * The actual scroll-anchor math lives in `ChatScrollPaginator` inside
 * `chat-view.tsx`. We:
 *   - Mock `@/components/assistant-ui/thread` so we render a plain DOM stub
 *     with the `data-slot="aui_thread-viewport"` selector the paginator looks
 *     up. This keeps the test scoped to our wrapper, not the vendored thread.
 *   - Mock `AssistantRuntimeProvider` so it just renders children — no real
 *     runtime context required.
 *   - Stub `useFridgeRuntime` so we can drive `pagination.loadOlder()` and
 *     `hasMore`/`isLoadingOlder` ourselves, plus assert the wrapper restores
 *     `scrollTop` after the prepend.
 *
 * The assertion is: `scrollTop` AFTER the prepend equals
 * `prevScrollTop + (newScrollHeight - prevScrollHeight)` to within 1px. The
 * wrapper does this in a double-rAF; we drive rAF manually via fake timers
 * + `vi.spyOn(window, "requestAnimationFrame")`.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import type { ReactNode } from "react";

// IMPORTANT: hoisted mocks must be declared before the component import.
const loadOlderMock = vi.fn<() => Promise<number>>();
let viewportEl: HTMLElement | null = null;

vi.mock("@assistant-ui/react", async () => {
  return {
    // ChatView passes the runtime in; we render children directly.
    AssistantRuntimeProvider: ({ children }: { children: ReactNode }) => (
      <div data-testid="runtime-provider">{children}</div>
    ),
  };
});

vi.mock("@/components/assistant-ui/thread", () => ({
  // The paginator queries `[data-slot="aui_thread-viewport"]` on its wrapper.
  // We render a div carrying that selector and capture the element so the
  // test can manipulate scrollTop / scrollHeight before/after the prepend.
  Thread: () => (
    <div
      data-slot="aui_thread-viewport"
      ref={(el) => {
        viewportEl = el;
      }}
      data-testid="thread-viewport"
      style={{ overflow: "auto", height: 400 }}
    />
  ),
}));

const useFridgeRuntimeMock = vi.fn();
vi.mock("@/lib/use-fridge-runtime", () => ({
  useFridgeRuntime: () => useFridgeRuntimeMock(),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

// Provide a working listThreads / createThread response so ChatView's
// bootstrapping resolves to a thread id.
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw-server";
import { saveToken } from "@/lib/auth";
import { ChatView } from "@/components/fridge/chat-view";

const BACKEND = "http://localhost:8001";

beforeEach(() => {
  saveToken("eyJhbGciOiJub25lIn0.eyJmYW1pbHlfaWQiOiJmYW0tMSJ9.x");
  loadOlderMock.mockReset();
  viewportEl = null;

  // Give ChatView a thread to open.
  server.use(
    http.get(`${BACKEND}/threads`, () =>
      HttpResponse.json([
        {
          id: 100,
          thread_id: "uuid-100",
          title: "T",
          created_at: "2026-04-20T10:00:00Z",
          updated_at: "2026-04-24T12:00:00Z",
        },
      ]),
    ),
  );
});

afterEach(() => vi.restoreAllMocks());

/**
 * Helper: configure the mocked `useFridgeRuntime` return for one render.
 * We don't need a real `runtime` object — the AssistantRuntimeProvider mock
 * ignores it.
 */
function configureRuntime(opts: {
  hasMore: boolean;
  hasLoadedInitial?: boolean;
  isLoading?: boolean;
  isLoadingOlder?: boolean;
}) {
  useFridgeRuntimeMock.mockReturnValue({
    runtime: {} as unknown,
    pagination: {
      isLoading: opts.isLoading ?? false,
      isLoadingOlder: opts.isLoadingOlder ?? false,
      hasMore: opts.hasMore,
      hasLoadedInitial: opts.hasLoadedInitial ?? true,
      loadOlder: loadOlderMock,
    },
    threadUuid: "uuid-100",
  });
}

/**
 * Drive both rAFs the paginator schedules (it uses double-rAF to wait for the
 * DOM to settle after React commits the prepend). We pre-stub
 * `requestAnimationFrame` so callbacks fire synchronously inside `flushRaf`.
 */
function setupRafStub() {
  const rafQueue: FrameRequestCallback[] = [];
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    rafQueue.push(cb);
    return rafQueue.length;
  });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
  return {
    flushRaf() {
      const queued = rafQueue.splice(0);
      queued.forEach((cb) => cb(performance.now()));
    },
  };
}

describe("[component] ChatView scroll-anchor restoration", () => {
  test("preserves user's scroll position after prepending an older page", async () => {
    configureRuntime({ hasMore: true });
    const raf = setupRafStub();

    render(<ChatView onVoiceClick={() => undefined} />);

    // ChatView fetches /threads then mounts the paginator + Thread; let those
    // microtasks settle.
    await screen.findByTestId("thread-viewport");
    expect(viewportEl).not.toBeNull();
    const node = viewportEl as unknown as HTMLElement;

    // jsdom doesn't size elements; assign scrollTop/scrollHeight via Object.defineProperty.
    Object.defineProperty(node, "scrollHeight", {
      configurable: true,
      get() {
        return (node as unknown as { __h: number }).__h ?? 1000;
      },
    });
    (node as unknown as { __h: number }).__h = 1000;
    Object.defineProperty(node, "clientHeight", {
      configurable: true,
      value: 400,
    });
    node.scrollTop = 30; // user scrolled near the top, within the 80px threshold

    // Paginator polls every 50ms for the viewport via setInterval; in jsdom
    // the polling is on real timers, but tryAttach succeeds on the first
    // synchronous run since we render the viewport child eagerly. Just to be
    // safe, dispatch a scroll event right away.
    loadOlderMock.mockImplementation(async () => {
      // Simulate the prepend by growing scrollHeight. The actual messages
      // array is owned by useFridgeRuntime (mocked) — what the paginator cares
      // about is only that scrollHeight changed.
      (node as unknown as { __h: number }).__h = 1500;
      return 30;
    });

    // Fire a scroll near the top — the listener triggers loadOlder().
    await act(async () => {
      node.dispatchEvent(new Event("scroll"));
    });
    // Let the loadOlder promise resolve.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(loadOlderMock).toHaveBeenCalledTimes(1);

    // Now drive the double-rAF that performs the scroll restoration.
    await act(async () => {
      raf.flushRaf(); // outer rAF schedules inner rAF
      raf.flushRaf(); // inner rAF runs the scrollTop adjustment
    });

    // Assert: scrollTop is restored to prev + (newHeight - prevHeight)
    //   = 30 + (1500 - 1000) = 530. Allow ±5px slack per the brief.
    expect(node.scrollTop).toBeGreaterThanOrEqual(525);
    expect(node.scrollTop).toBeLessThanOrEqual(535);
  });

  test("does not call loadOlder when the user is far from the top", async () => {
    configureRuntime({ hasMore: true });
    setupRafStub();

    render(<ChatView onVoiceClick={() => undefined} />);
    await screen.findByTestId("thread-viewport");
    const node = viewportEl as unknown as HTMLElement;
    Object.defineProperty(node, "scrollHeight", {
      configurable: true,
      value: 1000,
    });
    Object.defineProperty(node, "clientHeight", {
      configurable: true,
      value: 400,
    });
    node.scrollTop = 500; // well below 80px threshold

    await act(async () => {
      node.dispatchEvent(new Event("scroll"));
    });
    expect(loadOlderMock).not.toHaveBeenCalled();
  });

  test("shows 'beginning of conversation' pill only after user reaches the top with no more pages", async () => {
    // hasMore=false but the user hasn't yet scrolled to the top.
    configureRuntime({ hasMore: false });
    setupRafStub();

    const { rerender } = render(<ChatView onVoiceClick={() => undefined} />);
    await screen.findByTestId("thread-viewport");

    // Pill must NOT render on initial open of a short thread (atTop is still false).
    expect(
      screen.queryByText(/beginning of the conversation/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/loading earlier messages/i)).not.toBeInTheDocument();

    // Simulate the user scrolling all the way to the top.
    const node = viewportEl as unknown as HTMLElement;
    Object.defineProperty(node, "scrollHeight", {
      configurable: true,
      value: 800,
    });
    Object.defineProperty(node, "clientHeight", {
      configurable: true,
      value: 400,
    });
    node.scrollTop = 0;

    await act(async () => {
      node.dispatchEvent(new Event("scroll"));
    });

    // Re-render is required to flush atTop state into the JSX.
    rerender(<ChatView onVoiceClick={() => undefined} />);

    // After scrolling to top with hasMore=false, the start pill renders.
    expect(
      screen.getByText(/beginning of the conversation/i),
    ).toBeInTheDocument();
    // loadOlder must NOT have fired (no more pages).
    expect(loadOlderMock).not.toHaveBeenCalled();
  });

  test("renders the loading pill while a page is in flight", async () => {
    configureRuntime({ hasMore: true, isLoadingOlder: true });
    setupRafStub();
    render(<ChatView onVoiceClick={() => undefined} />);
    await screen.findByTestId("thread-viewport");

    expect(screen.getByText(/loading earlier messages/i)).toBeInTheDocument();
  });
});
