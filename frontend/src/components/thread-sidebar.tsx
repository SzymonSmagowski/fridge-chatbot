"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { LogOutIcon, MessageSquarePlusIcon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient, ApiError, type ThreadResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages.js";

export type ThreadSidebarProps = {
  selectedThreadId: number | null;
  onSelect: (threadId: number | null) => void;
  onCreate: () => void;
  username: string | null;
  onLogout: () => void;
  refreshKey?: number;
};

export function ThreadSidebar({
  selectedThreadId,
  onSelect,
  onCreate,
  username,
  onLogout,
  refreshKey,
}: ThreadSidebarProps) {
  const [threads, setThreads] = useState<ThreadResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await apiClient.listThreads();
      setThreads(list);
      setError(null);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : m.errors_load_threads_failed();
      setError(msg);
      setThreads([]);
    }
  }, []);

  useEffect(() => {
    // setState happens inside the awaited callback, not in the effect body —
    // known false positive of the React 19 `react-hooks/set-state-in-effect` rule.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load, refreshKey]);

  const onDelete = async (id: number) => {
    try {
      await apiClient.deleteThread(id);
      if (selectedThreadId === id) onSelect(null);
      await load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : m.errors_delete_thread_failed();
      toast.error(msg);
    }
  };

  return (
    <aside className="flex w-64 flex-col border-r bg-muted/30">
      <div className="p-3">
        <Button
          onClick={onCreate}
          className="w-full justify-start gap-2"
          variant="outline"
        >
          <MessageSquarePlusIcon className="size-4" />
          {m.thread_sidebar_new_chat()}
        </Button>
      </div>
      <Separator />
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-1 p-2">
          {threads === null ? (
            Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))
          ) : threads.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              {error ?? m.thread_sidebar_empty()}
            </p>
          ) : (
            threads.map((t) => (
              <div
                key={t.id}
                className={cn(
                  "group flex h-9 items-center gap-1 rounded-md transition-colors hover:bg-muted",
                  selectedThreadId === t.id && "bg-muted",
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect(t.id)}
                  className="flex min-w-0 flex-1 items-center px-3 text-left text-sm"
                >
                  <span className="truncate">
                    {t.title ?? m.thread_sidebar_default_title()}
                  </span>
                </button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => onDelete(t.id)}
                  className="mr-1 size-7 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-label={m.thread_sidebar_delete_aria()}
                >
                  <Trash2Icon className="size-4" />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
      <Separator />
      <div className="flex items-center justify-between gap-2 p-3 text-sm">
        <span className="truncate text-muted-foreground">
          {username ?? m.common_signed_out()}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onLogout}
          aria-label={m.auth_sign_out_aria()}
        >
          <LogOutIcon className="size-4" />
        </Button>
      </div>
    </aside>
  );
}
