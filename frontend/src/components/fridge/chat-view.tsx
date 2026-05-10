"use client";
import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { toast } from "sonner";
import { Thread } from "@/components/assistant-ui/thread";
import { useFridgeRuntime } from "@/lib/use-fridge-runtime";
import { ApiError, apiClient, type ThreadResponse } from "@/lib/api";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

type Props = {
  /**
   * Opens the voice overlay. Owned by `app-shell` (not chat-view) so the
   * wake-word listener can open the same overlay from any tab.
   */
  onVoiceClick: () => void;
};

/**
 * Chat tab — wraps the existing assistant-ui <Thread /> + custom WS runtime.
 * Per design doc §3.3 production wiring note, this view does NOT replace the
 * assistant-ui Thread with the design's mock chat — it reuses production code
 * and wraps it in the device shell.
 *
 * Auto-resolves a "current" thread: lists existing threads, picks the most
 * recent, or creates a new "Fridge chat" thread on first load.
 *
 * Voice mode is opened from inside the chat composer (mic button next to
 * Send) — this view just forwards the request up to `app-shell`, which owns
 * the overlay state so wake-word activation can open it too.
 */
export function ChatView({ onVoiceClick }: Props) {
  const [threadId, setThreadId] = useState<number | null>(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const runtime = useFridgeRuntime(threadId);

  const ensureThread = useCallback(async () => {
    try {
      const list = await apiClient.listThreads();
      if (list.length > 0) {
        const sorted = [...list].sort(
          (a: ThreadResponse, b: ThreadResponse) =>
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
        );
        setThreadId(sorted[0].id);
      } else {
        const created = await apiClient.createThread(m.chat_default_thread_title());
        setThreadId(created.id);
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_open_chat_failed();
      toast.error(msg);
    } finally {
      setBootstrapping(false);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount only. setState happens inside the awaited callback —
    // known false positive of `react-hooks/set-state-in-effect` for this idiom.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void ensureThread();
  }, [ensureThread]);

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-chat"
      aria-labelledby="tab-chat"
    >
      <div className={styles.chatWrap}>
        <div className={styles.chatHero}>
          <div className={styles.aiCrest} aria-hidden="true">
            <Sparkles size={28} strokeWidth={2} color="#fff" />
          </div>
          <h3>{m.chat_hero_title()}</h3>
          <p>{m.chat_hero_subtitle()}</p>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
          {bootstrapping || threadId == null ? (
            <div style={{ padding: 32, textAlign: "center", color: "var(--muted-fg)" }}>
              {m.chat_opening()}
            </div>
          ) : (
            <AssistantRuntimeProvider runtime={runtime}>
              <Thread onVoiceClick={onVoiceClick} />
            </AssistantRuntimeProvider>
          )}
        </div>
      </div>
    </section>
  );
}
