"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import type { AssigneeSelection } from "./assignee-picker";
import { ErrorBanner } from "./error-banner";
import { joinTitleAndBody } from "./notes-content";
import { NoteEditorPane } from "./note-editor-pane";
import { NotesHeroStrip } from "./notes-hero-strip";
import { NotesListPane } from "./notes-list-pane";
import { NotesSkeleton } from "./notes-skeleton";
import { TabHeader } from "./tab-header";
import { useNoteAutosave } from "./use-note-autosave";
import { WeatherChip } from "./weather-chip";
import { useFamilyEvents } from "@/lib/use-family-events";
import {
  ApiError,
  notesApi,
  SHOPPING_LIST_SLUG,
  type CarResponse,
  type MemberResponse,
  type NoteResponse,
} from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export interface NotesViewProps {
  members: MemberResponse[];
  cars: CarResponse[];
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return m.greeting_night();
  if (h < 12) return m.greeting_morning();
  if (h < 18) return m.greeting_afternoon();
  return m.greeting_evening();
}

export function NotesView({ members, cars }: NotesViewProps) {
  const [notes, setNotes] = useState<NoteResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null);
  const creatingRef = useRef(false);

  const sortedNotes = useMemo(() => {
    if (!notes) return [];
    return notes
      .slice()
      .sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
  }, [notes]);

  const heroNotes = useMemo(() => sortedNotes.slice(0, 2), [sortedNotes]);

  const fetchNotes = useCallback(async () => {
    try {
      const res = await notesApi.list({ limit: 200 });
      setNotes(res.items);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : m.errors_load_notes_failed();
      setError(message);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchNotes();
  }, [fetchNotes]);

  useFamilyEvents(fetchNotes);

  const autosave = useNoteAutosave({
    onSaved: (next) => {
      setNotes((prev) =>
        prev ? prev.map((n) => (n.id === next.id ? next : n)) : prev,
      );
    },
    onError: () => toast.error(m.errors_update_note_failed()),
  });

  const selected = useMemo(
    () => sortedNotes.find((n) => n.id === selectedId) ?? null,
    [sortedNotes, selectedId],
  );

  // Track the latest local content of the open note so we can detect "empty"
  // on close without waiting for the in-flight PATCH to settle.
  const localContentRef = useRef<{ id: string; content: string } | null>(null);

  const handleEditorChange = useCallback(
    (next: { title: string; body: string }) => {
      if (!selected) return;
      const content = joinTitleAndBody(next);
      localContentRef.current = { id: selected.id, content };
      // Optimistic list update.
      setNotes((prev) =>
        prev
          ? prev.map((n) =>
              n.id === selected.id
                ? { ...n, content, updated_at: new Date().toISOString() }
                : n,
            )
          : prev,
      );
      autosave.schedule(selected.id, { content });
    },
    [autosave, selected],
  );

  const handleAssigneeChange = useCallback(
    (next: AssigneeSelection) => {
      if (!selected) return;
      const assignee_member_id = next.kind === "member" ? next.id : null;
      setNotes((prev) =>
        prev
          ? prev.map((n) =>
              n.id === selected.id ? { ...n, assignee_member_id } : n,
            )
          : prev,
      );
      autosave.schedule(selected.id, { assignee_member_id });
    },
    [autosave, selected],
  );

  const handleCarToggle = useCallback(
    (carId: string) => {
      if (!selected) return;
      const has = selected.car_ids.includes(carId);
      const car_ids = has
        ? selected.car_ids.filter((c) => c !== carId)
        : [...selected.car_ids, carId];
      setNotes((prev) =>
        prev
          ? prev.map((n) => (n.id === selected.id ? { ...n, car_ids } : n))
          : prev,
      );
      autosave.schedule(selected.id, { car_ids });
    },
    [autosave, selected],
  );

  // Apple-Notes flow: Add → create empty note → focus title.
  const handleCreate = useCallback(async () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    autosave.cancel();
    // Empty-note cleanup before opening a new one.
    await maybeDeleteIfEmpty();
    try {
      const created = await notesApi.create({ content: "" });
      setNotes((prev) => (prev ? [created, ...prev] : [created]));
      setSelectedId(created.id);
      setJustCreatedId(created.id);
      localContentRef.current = { id: created.id, content: "" };
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_add_note_failed();
      toast.error(msg);
    } finally {
      creatingRef.current = false;
    }
    // maybeDeleteIfEmpty needs to be in scope; defined below via closure trick.
    async function maybeDeleteIfEmpty() {
      const local = localContentRef.current;
      if (!local) return;
      // Only kill notes that are still empty AND were freshly created.
      if (local.content.trim().length > 0) return;
      const target = notes?.find((n) => n.id === local.id);
      if (!target) return;
      // Don't delete the special shopping note.
      if (target.labels.some((l) => l.slug === SHOPPING_LIST_SLUG)) return;
      try {
        await notesApi.delete(local.id);
        setNotes((prev) => (prev ? prev.filter((n) => n.id !== local.id) : prev));
      } catch {
        // best-effort cleanup
      }
      localContentRef.current = null;
    }
  }, [autosave, notes]);

  const handleCreateShoppingList = useCallback(async () => {
    try {
      const created = await notesApi.create({
        content: "",
        label_slugs: [SHOPPING_LIST_SLUG],
        pinned: true,
      });
      setNotes((prev) => (prev ? [created, ...prev] : [created]));
      setSelectedId(created.id);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_add_note_failed();
      toast.error(msg);
    }
  }, []);

  const cleanupEmptyOpenNote = useCallback(async () => {
    const local = localContentRef.current;
    if (!local) return;
    if (local.content.trim().length > 0) return;
    const target = notes?.find((n) => n.id === local.id);
    if (!target) return;
    if (target.labels.some((l) => l.slug === SHOPPING_LIST_SLUG)) return;
    try {
      await notesApi.delete(local.id);
      setNotes((prev) => (prev ? prev.filter((n) => n.id !== local.id) : prev));
    } catch {
      // best-effort
    }
    localContentRef.current = null;
  }, [notes]);

  const handleSelect = useCallback(
    async (id: string) => {
      if (id === selectedId) return;
      autosave.cancel();
      await cleanupEmptyOpenNote();
      setSelectedId(id);
      setJustCreatedId(null);
      const target = notes?.find((n) => n.id === id);
      if (target) localContentRef.current = { id, content: target.content };
    },
    [autosave, cleanupEmptyOpenNote, notes, selectedId],
  );

  const handleDelete = useCallback(async () => {
    if (!selected) return;
    if (selected.labels.some((l) => l.slug === SHOPPING_LIST_SLUG)) return;
    autosave.cancel();
    const id = selected.id;
    setNotes((prev) => (prev ? prev.filter((n) => n.id !== id) : prev));
    setSelectedId(null);
    localContentRef.current = null;
    try {
      await notesApi.delete(id);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_update_note_failed();
      toast.error(msg);
      void fetchNotes();
    }
  }, [autosave, fetchNotes, selected]);

  const hasShoppingList = useMemo(
    () =>
      sortedNotes.some((n) => n.labels.some((l) => l.slug === SHOPPING_LIST_SLUG)),
    [sortedNotes],
  );

  const isLoading = notes === null && !error;
  const isEmpty = notes !== null && notes.length === 0;

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-notes"
      aria-labelledby="tab-notes"
    >
      <TabHeader
        eyebrow={m.notes_eyebrow()}
        title={m.notes_title({ greeting: greeting() })}
        right={<WeatherChip />}
      />

      <div className={styles.notesScroll}>
        {error ? (
          <ErrorBanner message={error} onRetry={() => void fetchNotes()} />
        ) : null}

        {isLoading ? (
          <NotesSkeleton count={4} />
        ) : isEmpty ? (
          <EmptyBoard onAddFirst={() => void handleCreate()} />
        ) : (
          <>
            <NotesHeroStrip
              notes={heroNotes}
              selectedId={selectedId}
              onOpen={(id) => void handleSelect(id)}
            />

            <div className={styles.notesWorkspace}>
              <NotesListPane
                notes={sortedNotes}
                selectedId={selectedId}
                hasShoppingList={hasShoppingList}
                onSelect={(id) => void handleSelect(id)}
                onCreate={() => void handleCreate()}
                onCreateShoppingList={() => void handleCreateShoppingList()}
              />

              <div className={styles.notesEditorWrap}>
                {selected ? (
                  <NoteEditorPane
                    note={selected}
                    members={members}
                    cars={cars}
                    isJustCreated={selected.id === justCreatedId}
                    onChange={handleEditorChange}
                    onAssigneeChange={handleAssigneeChange}
                    onCarToggle={handleCarToggle}
                    onDelete={() => void handleDelete()}
                  />
                ) : (
                  <EditorPlaceholder onCreate={() => void handleCreate()} />
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function EditorPlaceholder({ onCreate }: { onCreate: () => void }) {
  return (
    <div className={styles.notesEditorPlaceholder}>
      <div className={styles.notesEditorPlaceholderInner}>
        <div className={styles.notesEditorPlaceholderTitle}>
          {m.notes_editor_placeholder_title()}
        </div>
        <p className={styles.notesEditorPlaceholderHint}>
          {m.notes_editor_placeholder_hint()}
        </p>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={onCreate}
        >
          {m.notes_editor_placeholder_button()}
        </button>
      </div>
    </div>
  );
}

function EmptyBoard({ onAddFirst }: { onAddFirst: () => void }) {
  return (
    <div
      style={{
        padding: 48,
        textAlign: "center",
        border: "2px dashed var(--border-color)",
        borderRadius: "var(--radius-card)",
        color: "var(--muted-fg)",
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>
        {m.notes_empty_board_title()}
      </div>
      <div style={{ marginTop: 8, marginBottom: 16 }}>
        {m.notes_empty_board_hint()}
      </div>
      <button
        type="button"
        className={`${styles.btn} ${styles.btnPrimary}`}
        onClick={onAddFirst}
      >
        {m.notes_empty_board_button()}
      </button>
    </div>
  );
}
