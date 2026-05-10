"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { toast } from "sonner";
import {
  apiClient,
  wsUrl,
  type MessageResponse,
  ApiError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

function messageToLike(msg: MessageResponse): ThreadMessageLike {
  const role: ThreadMessageLike["role"] =
    msg.role === "assistant" || msg.role === "system" ? msg.role : "user";
  return {
    id: msg.id,
    role,
    content: [{ type: "text", text: msg.content }],
    createdAt: msg.created_at ? new Date(msg.created_at) : undefined,
  };
}

/**
 * Reverse a newest-first wire array to the chronological (oldest-first) order
 * that `useExternalStoreRuntime` renders top-to-bottom inside the scroll
 * viewport. Done in one place so the rest of the runtime can stay agnostic to
 * wire order.
 */
function pageToChronological(messages: MessageResponse[]): ThreadMessageLike[] {
  const out: ThreadMessageLike[] = new Array(messages.length);
  for (let i = 0; i < messages.length; i++) {
    out[messages.length - 1 - i] = messageToLike(messages[i]);
  }
  return out;
}

export interface FridgeRuntimePagination {
  /** True while the initial-page hydrate is in flight. */
  isLoading: boolean;
  /** True while a `loadOlder` page is in flight. */
  isLoadingOlder: boolean;
  /** Are there more (older) messages on the server? */
  hasMore: boolean;
  /** Have we hydrated at least once for this thread? */
  hasLoadedInitial: boolean;
  /**
   * Fetch the next-older page and prepend it. Caller is responsible for
   * capturing scroll position before calling and restoring it after — we don't
   * own the viewport here. Returns the count of newly prepended messages so the
   * caller can no-op when there's nothing to do.
   */
  loadOlder: () => Promise<number>;
}

export interface UseFridgeRuntimeResult {
  runtime: ReturnType<typeof useExternalStoreRuntime<ThreadMessageLike>>;
  pagination: FridgeRuntimePagination;
  /** UUID of the active thread, used by feedback submission to attach context. */
  threadUuid: string | null;
}

/**
 * Custom assistant-ui runtime backed by REST + WebSocket. Owns:
 *   - thread message state (oldest-first, the order assistant-ui renders),
 *   - lazy pagination of older history,
 *   - the streaming WebSocket lifecycle for outgoing user turns.
 *
 * Pagination contract (matches Architect §A): the server returns newest-first
 * with a `next_cursor` pointing at the oldest message in the page; we reverse
 * each page to chronological and prepend.
 */
export function useFridgeRuntime(threadId: number | null): UseFridgeRuntimeResult {
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [hasLoadedInitial, setHasLoadedInitial] = useState(false);
  const [threadUuid, setThreadUuid] = useState<string | null>(null);

  // Cursor + in-flight guard live in refs — they never need to trigger a
  // re-render, and the loadOlder callback should keep a stable identity so
  // chat-view's scroll listener doesn't churn.
  const nextCursorRef = useRef<string | null>(null);
  const hasMoreRef = useRef(false);
  const loadingOlderRef = useRef(false);
  const threadIdRef = useRef<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pendingAssistantIdRef = useRef<string | null>(null);

  useEffect(() => {
    threadIdRef.current = threadId;
    if (threadId == null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([]);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHasMore(false);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHasLoadedInitial(false);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setThreadUuid(null);
      nextCursorRef.current = null;
      hasMoreRef.current = false;
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setHasLoadedInitial(false);
    apiClient
      .getThread(threadId)
      .then((thread) => {
        if (cancelled) return;
        setMessages(pageToChronological(thread.messages));
        setHasMore(thread.has_more);
        setThreadUuid(thread.thread_id);
        nextCursorRef.current = thread.next_cursor;
        hasMoreRef.current = thread.has_more;
        setHasLoadedInitial(true);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError ? err.message : "Failed to load thread";
        toast.error(msg);
        setMessages([]);
        setHasMore(false);
        setThreadUuid(null);
        nextCursorRef.current = null;
        hasMoreRef.current = false;
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  const loadOlder = useCallback(async (): Promise<number> => {
    const tid = threadIdRef.current;
    if (tid == null) return 0;
    if (loadingOlderRef.current) return 0;
    if (!hasMoreRef.current) return 0;
    const cursor = nextCursorRef.current;
    if (!cursor) return 0;

    loadingOlderRef.current = true;
    setIsLoadingOlder(true);
    try {
      const page = await apiClient.getThreadMessagesPage(tid, {
        before: cursor,
        limit: 30,
      });
      const olderChrono = pageToChronological(page.messages);
      setMessages((prev) => [...olderChrono, ...prev]);
      nextCursorRef.current = page.next_cursor;
      hasMoreRef.current = page.has_more;
      setHasMore(page.has_more);
      return olderChrono.length;
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Failed to load earlier messages";
      toast.error(msg);
      return 0;
    } finally {
      loadingOlderRef.current = false;
      setIsLoadingOlder(false);
    }
  }, []);

  const appendAssistantToken = useCallback((token: string) => {
    const id = pendingAssistantIdRef.current;
    if (!id) return;
    setMessages((prev) => {
      const idx = prev.findIndex((msg) => msg.id === id);
      if (idx === -1) return prev;
      const target = prev[idx];
      const previousText =
        Array.isArray(target.content) && target.content[0]?.type === "text"
          ? target.content[0].text
          : "";
      const next = prev.slice();
      next[idx] = {
        ...target,
        content: [{ type: "text", text: previousText + token }],
      };
      return next;
    });
  }, []);

  const onNew = useCallback(
    async (message: AppendMessage) => {
      if (threadId == null) {
        toast.error("No thread selected");
        return;
      }
      const token = getToken();
      if (!token) {
        toast.error("You are not signed in");
        return;
      }
      if (message.content.length !== 1 || message.content[0]?.type !== "text") {
        toast.error("Only text messages are supported");
        return;
      }

      const userText = message.content[0].text;
      const userId = `user-${Date.now()}`;
      const assistantId = `assistant-${Date.now()}`;
      pendingAssistantIdRef.current = assistantId;

      setMessages((prev) => [
        ...prev,
        {
          id: userId,
          role: "user",
          content: [{ type: "text", text: userText }],
          createdAt: new Date(),
        },
        {
          id: assistantId,
          role: "assistant",
          content: [{ type: "text", text: "" }],
          createdAt: new Date(),
        },
      ]);

      setIsRunning(true);

      await new Promise<void>((resolve) => {
        const ws = new WebSocket(wsUrl(threadId));
        wsRef.current = ws;

        ws.addEventListener("open", () => {
          ws.send(JSON.stringify({ content: userText, token }));
        });

        ws.addEventListener("message", (ev) => {
          let data: unknown;
          try {
            data = JSON.parse(ev.data as string);
          } catch {
            return;
          }
          if (!data || typeof data !== "object") return;
          const payload = data as {
            type?: string;
            content?: string;
            message?: string;
            error?: string;
          };
          if (payload.error) {
            toast.error(payload.error);
            return;
          }
          if (payload.type === "error_notification") {
            toast.error(payload.message ?? "An error occurred");
            return;
          }
          if (payload.type === "message" && typeof payload.content === "string") {
            appendAssistantToken(payload.content);
          }
        });

        const finish = () => {
          setIsRunning(false);
          pendingAssistantIdRef.current = null;
          wsRef.current = null;
          resolve();
        };

        ws.addEventListener("close", finish);
        ws.addEventListener("error", () => {
          toast.error("Connection error");
          try {
            ws.close();
          } catch {
            // ignore
          }
          finish();
        });
      });
    },
    [threadId, appendAssistantToken],
  );

  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    isLoading,
    isRunning,
    messages,
    setMessages,
    convertMessage: (msg) => msg,
    onNew,
  });

  return {
    runtime,
    pagination: {
      isLoading,
      isLoadingOlder,
      hasMore,
      hasLoadedInitial,
      loadOlder,
    },
    threadUuid,
  };
}
