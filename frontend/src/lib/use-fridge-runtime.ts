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

export function useFridgeRuntime(threadId: number | null) {
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingAssistantIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (threadId == null) {
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

  return runtime;
}
