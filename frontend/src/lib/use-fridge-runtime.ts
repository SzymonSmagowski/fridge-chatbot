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

function messageToLike(m: MessageResponse): ThreadMessageLike {
  const role: ThreadMessageLike["role"] =
    m.role === "assistant" || m.role === "system" ? m.role : "user";
  return {
    id: m.id,
    role,
    content: [{ type: "text", text: m.content }],
    createdAt: m.created_at ? new Date(m.created_at) : undefined,
  };
}

type PendingAssistant = {
  id: string;
  text: string;
};

export function useFridgeRuntime(threadId: number | null) {
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<PendingAssistant | null>(null);

  useEffect(() => {
    if (threadId == null) {
      // Reset on thread change — external-sync pattern; false positive of
      // React 19's `react-hooks/set-state-in-effect` rule.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([]);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    apiClient
      .getThread(threadId)
      .then((thread) => {
        if (cancelled) return;
        setMessages(thread.messages.map(messageToLike));
      })
      .catch((err) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError ? err.message : "Failed to load thread";
        toast.error(msg);
        setMessages([]);
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

  const appendMessage = useCallback((msg: ThreadMessageLike) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const updatePendingAssistant = useCallback((text: string) => {
    const pending = pendingRef.current;
    if (!pending) return;
    pending.text = text;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === pending.id);
      if (idx === -1) return prev;
      const next = prev.slice();
      next[idx] = {
        ...next[idx],
        content: [{ type: "text", text }],
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
      appendMessage({
        id: `local-user-${Date.now()}`,
        role: "user",
        content: [{ type: "text", text: userText }],
        createdAt: new Date(),
      });

      const assistantId = `local-assistant-${Date.now()}`;
      pendingRef.current = { id: assistantId, text: "" };
      appendMessage({
        id: assistantId,
        role: "assistant",
        content: [{ type: "text", text: "" }],
        createdAt: new Date(),
      });

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
            status?: string;
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
            const pending = pendingRef.current;
            if (!pending) return;
            updatePendingAssistant(pending.text + payload.content);
          }
        });

        const finish = () => {
          setIsRunning(false);
          pendingRef.current = null;
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

      // After stream completes, refetch the thread so we pick up the real
      // assistant message id (needed for feedback).
      try {
        const fresh = await apiClient.getThread(threadId);
        setMessages(fresh.messages.map(messageToLike));
      } catch {
        // keep local streamed state if refetch fails
      }
    },
    [threadId, appendMessage, updatePendingAssistant],
  );

  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    isLoading,
    isRunning,
    messages,
    setMessages,
    convertMessage: (m) => m,
    onNew,
  });

  return runtime;
}
