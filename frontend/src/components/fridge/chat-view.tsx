"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { toast } from "sonner";
import { Thread } from "@/components/assistant-ui/thread";
import {
  useFridgeRuntime,
  type FridgeRuntimePagination,
} from "@/lib/use-fridge-runtime";
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

/** Pixels from top of the viewport at which we trigger a `loadOlder` page. */
const LOAD_OLDER_THRESHOLD_PX = 80;

/**
 * Chat tab — wraps the existing assistant-ui <Thread /> + custom WS runtime.
 * Auto-resolves a "current" thread, hydrates the latest 30 messages on open,
 * and lazy-loads older history when the user scrolls to the top.
 *
 * Voice mode is opened from inside the chat composer; this view just forwards
 * the request up to `app-shell`, which owns the overlay state so wake-word
 * activation can open it too.
 */
export function ChatView({ onVoiceClick }: Props) {
  const [threadId, setThreadId] = useState<number | null>(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const { runtime, pagination } = useFridgeRuntime(threadId);

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
              <ChatScrollPaginator pagination={pagination} threadKey={threadId}>
                <Thread onVoiceClick={onVoiceClick} />
              </ChatScrollPaginator>
            </AssistantRuntimeProvider>
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * Wraps <Thread /> with the scroll-to-top → load-older behavior. Sits inside
 * the AssistantRuntimeProvider so it can wait for assistant-ui to mount its
 * viewport before attaching listeners. We deliberately don't use an
 * IntersectionObserver — the assistant-ui viewport mounts an internal sticky
 * composer footer that interferes with top-anchored sentinels; a direct
 * scrollTop check on the viewport is both simpler and more accurate.
 *
 * Scroll-anchor: before prepending an older page we capture
 * `(scrollTop, scrollHeight)`; two animation frames after the DOM has the new
 * rows, we restore `scrollTop = newScrollHeight - oldScrollHeight +
 * oldScrollTop`. Without this the user's reading position jumps — the
 * make-or-break UX detail.
 */
function ChatScrollPaginator({
  pagination,
  threadKey,
  children,
}: {
  pagination: FridgeRuntimePagination;
  threadKey: number;
  children: React.ReactNode;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef<HTMLElement | null>(null);
  const [atTop, setAtTop] = useState(false);

  // Latest pagination behind a ref so the scroll listener can stay installed
  // for the wrapper's lifetime. Synced via effect to satisfy React 19's
  // "no ref writes during render" rule.
  const paginationRef = useRef(pagination);
  useEffect(() => {
    paginationRef.current = pagination;
  });

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    let detach: (() => void) | undefined;

    const tryAttach = (): boolean => {
      const el = wrap.querySelector<HTMLElement>(
        '[data-slot="aui_thread-viewport"]',
      );
      if (!el) return false;
      viewportRef.current = el;

      const onScroll = () => {
        const node = viewportRef.current;
        if (!node) return;
        const nearTop = node.scrollTop <= LOAD_OLDER_THRESHOLD_PX;
        setAtTop(nearTop);
        const p = paginationRef.current;
        if (!nearTop) return;
        if (!p.hasMore || p.isLoadingOlder || p.isLoading) return;

        const prevScrollTop = node.scrollTop;
        const prevScrollHeight = node.scrollHeight;
        void p.loadOlder().then((added) => {
          if (added <= 0) return;
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              const v = viewportRef.current;
              if (!v) return;
              const delta = v.scrollHeight - prevScrollHeight;
              v.scrollTop = prevScrollTop + delta;
            });
          });
        });
      };

      el.addEventListener("scroll", onScroll, { passive: true });
      detach = () => el.removeEventListener("scroll", onScroll);
      return true;
    };

    if (tryAttach()) return () => detach?.();

    // assistant-ui mounts the viewport asynchronously; poll briefly for it.
    let tries = 0;
    const id = window.setInterval(() => {
      tries += 1;
      if (tryAttach() || tries > 40) {
        window.clearInterval(id);
      }
    }, 50);

    return () => {
      window.clearInterval(id);
      detach?.();
    };
    // Re-attach when the active thread changes — the viewport DOM may be
    // recycled but its scroll position resets.
  }, [threadKey]);

  // The pill is shown either while a page is loading, or when the user has
  // scrolled to the very top of an exhausted history. We never show "Beginning
  // of conversation" before the user has reached the top, to avoid noise on
  // short threads.
  const showLoading = pagination.isLoadingOlder;
  const showStart =
    !showLoading && atTop && pagination.hasLoadedInitial && !pagination.hasMore;

  return (
    <div ref={wrapRef} className={styles.chatScrollPaginatorRoot}>
      {(showLoading || showStart) ? (
        <div
          className={styles.chatHistoryHint}
          aria-live="polite"
          role="status"
        >
          {showLoading ? (
            <>
              <span className={styles.chatHistorySpinner} aria-hidden="true" />
              <span>{m.chat_loading_older()}</span>
            </>
          ) : (
            <span>{m.chat_history_start()}</span>
          )}
        </div>
      ) : null}
      {children}
    </div>
  );
}
