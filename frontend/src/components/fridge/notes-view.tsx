"use client";
import { Clock, Pencil, Plus, Star } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { AddNoteCard } from "./add-note-card";
import { AssigneePicker, type AssigneeSelection } from "./assignee-picker";
import { ErrorBanner } from "./error-banner";
import { NoteCard } from "./note-card";
import { NotesSkeleton } from "./notes-skeleton";
import { TabHeader } from "./tab-header";
import { WeatherChip } from "./weather-chip";
import { toggleChecklistAt } from "./shopping-checklist";
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
  const [selected, setSelected] = useState<AssigneeSelection>({ kind: "family-wide" });
  const [quickInput, setQuickInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
    // Fetch-on-mount + refetch when filters change. setState happens inside the
    // awaited callback, not in the effect body — known false positive of the
    // React 19 `react-hooks/set-state-in-effect` rule for this idiom.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchNotes();
  }, [fetchNotes]);

  useFamilyEvents(fetchNotes);

  const pinned = useMemo(() => notes?.filter((n) => n.pinned) ?? [], [notes]);
  const recent = useMemo(() => notes?.filter((n) => !n.pinned) ?? [], [notes]);

  const handleQuickAdd = async () => {
    const text = quickInput.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    try {
      const created = await notesApi.create({
        content: text,
        assignee_member_id: selected.kind === "member" ? selected.id : null,
      });
      setNotes((prev) => (prev ? [created, ...prev] : [created]));
      setQuickInput("");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_add_note_failed();
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleChecklist = async (noteId: string, itemIndex: number) => {
    const target = notes?.find((n) => n.id === noteId);
    if (!target) return;
    const nextContent = toggleChecklistAt(target.content, itemIndex);
    // Optimistic update
    setNotes((prev) =>
      prev
        ? prev.map((n) => (n.id === noteId ? { ...n, content: nextContent } : n))
        : prev,
    );
    try {
      const updated = await notesApi.update(noteId, { content: nextContent });
      setNotes((prev) =>
        prev ? prev.map((n) => (n.id === noteId ? updated : n)) : prev,
      );
    } catch (err) {
      // Revert
      setNotes((prev) =>
        prev ? prev.map((n) => (n.id === noteId ? target : n)) : prev,
      );
      const msg = err instanceof ApiError ? err.message : m.errors_update_note_failed();
      toast.error(msg);
    }
  };

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

      <div className={styles.viewScroll}>
        <div className={styles.notesToolbar}>
          <Pencil
            size={22}
            strokeWidth={2}
            style={{ color: "var(--muted-fg)", marginLeft: 8 }}
            aria-hidden="true"
          />
          <input
            className={styles.quickInput}
            placeholder={m.notes_quick_add_placeholder()}
            value={quickInput}
            onChange={(e) => setQuickInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleQuickAdd();
            }}
            aria-label={m.notes_quick_add_aria()}
            disabled={submitting}
          />
          <AssigneePicker
            members={members}
            selected={selected}
            onSelect={setSelected}
          />
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimaryCompact}`}
            onClick={() => void handleQuickAdd()}
            disabled={submitting || !quickInput.trim()}
          >
            <Plus size={18} strokeWidth={2.4} />
            {m.notes_add_button()}
          </button>
        </div>

        {error ? <ErrorBanner message={error} onRetry={() => void fetchNotes()} /> : null}

        {isLoading ? (
          <>
            <SectionLabel
              title={m.notes_section_pinned()}
              count={0}
              icon={<Star size={14} fill="currentColor" strokeWidth={0} />}
            />
            <NotesSkeleton count={4} />
          </>
        ) : isEmpty ? (
          <EmptyBoard onAddFirst={() => void handleQuickAdd()} />
        ) : (
          <>
            <NotesSection
              title={m.notes_section_pinned()}
              count={pinned.length}
              icon={<Star size={14} fill="currentColor" strokeWidth={0} />}
            >
              {pinned.length === 0 ? (
                <EmptyInline label={m.notes_empty_pinned()} />
              ) : (
                <div className={styles.notesGrid}>
                  {pinned.map((n, i) => (
                    <NoteCard
                      key={n.id}
                      note={n}
                      members={members}
                      cars={cars}
                      cardIndex={i}
                      span={n.labels.some((l) => l.slug === SHOPPING_LIST_SLUG) ? 2 : 1}
                      onToggleChecklist={(id, idx) => void handleToggleChecklist(id, idx)}
                    />
                  ))}
                </div>
              )}
            </NotesSection>

            <NotesSection
              title={m.notes_section_recent()}
              count={recent.length}
              icon={<Clock size={14} strokeWidth={2.5} />}
            >
              <div className={styles.notesGrid}>
                {recent.map((n, i) => (
                  <NoteCard
                    key={n.id}
                    note={n}
                    members={members}
                    cars={cars}
                    cardIndex={i}
                    onToggleChecklist={(id, idx) => void handleToggleChecklist(id, idx)}
                  />
                ))}
                <AddNoteCard onClick={() => document.querySelector<HTMLInputElement>(`.${styles.quickInput}`)?.focus()} />
              </div>
            </NotesSection>
          </>
        )}
      </div>
    </section>
  );
}

function SectionLabel({
  title,
  count,
  icon,
}: {
  title: string;
  count: number;
  icon: React.ReactNode;
}) {
  return (
    <div className={styles.sectionLabel}>
      <span aria-hidden="true">{icon}</span>
      {title}
      <span className={styles.sectionCount}>{count}</span>
      <div className={styles.sectionDivider} />
    </div>
  );
}

function NotesSection({
  title,
  count,
  icon,
  children,
}: {
  title: string;
  count: number;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      <SectionLabel title={title} count={count} icon={icon} />
      {children}
    </>
  );
}

function EmptyInline({ label }: { label: string }) {
  return (
    <div
      style={{
        padding: 24,
        borderRadius: "var(--radius-card)",
        border: "2px dashed var(--border-color, #E8E0D4)",
        color: "var(--muted-fg)",
        textAlign: "center",
        marginBottom: 24,
      }}
    >
      {label}
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
