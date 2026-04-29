"use client";
import { useCallback, useEffect, useRef } from "react";
import { ApiError, notesApi, type NoteResponse, type NoteUpdateRequest } from "@/lib/api";

interface AutosaveOptions {
  delayMs?: number;
  onSaved?: (next: NoteResponse) => void;
  onError?: (err: unknown) => void;
}

interface AutosaveControls {
  schedule: (id: string, patch: NoteUpdateRequest) => void;
  flushNow: () => Promise<void>;
  cancel: () => void;
}

/**
 * Debounced auto-save with single-flight queueing.
 *
 * `schedule(id, patch)` resets the debounce timer; on fire we PATCH. If a
 * PATCH is already in flight we keep the latest pending payload and dispatch
 * it once the current one resolves — so we never lose the most recent edit
 * but never fire concurrent writes either.
 *
 * The whole state machine lives in refs because none of it should re-render
 * the caller. The exposed callbacks are stable across renders.
 */
export function useNoteAutosave({
  delayMs = 500,
  onSaved,
  onError,
}: AutosaveOptions = {}): AutosaveControls {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflightRef = useRef<Promise<void> | null>(null);
  const pendingRef = useRef<{ id: string; patch: NoteUpdateRequest } | null>(null);
  const onSavedRef = useRef(onSaved);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onSavedRef.current = onSaved;
    onErrorRef.current = onError;
  }, [onSaved, onError]);

  const flush = useCallback(async (): Promise<void> => {
    if (inflightRef.current) return;
    while (pendingRef.current) {
      const next = pendingRef.current;
      pendingRef.current = null;
      const run = (async () => {
        try {
          const updated = await notesApi.update(next.id, next.patch);
          onSavedRef.current?.(updated);
        } catch (err) {
          if (!(err instanceof ApiError) || err.status !== 404) {
            onErrorRef.current?.(err);
          }
        }
      })();
      inflightRef.current = run;
      try {
        await run;
      } finally {
        inflightRef.current = null;
      }
    }
  }, []);

  const schedule = useCallback(
    (id: string, patch: NoteUpdateRequest) => {
      pendingRef.current = { id, patch };
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void flush();
      }, delayMs);
    },
    [delayMs, flush],
  );

  const flushNow = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    await flush();
  }, [flush]);

  const cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { schedule, flushNow, cancel };
}
