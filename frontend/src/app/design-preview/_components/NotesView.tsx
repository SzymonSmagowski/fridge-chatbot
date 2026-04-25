"use client";
import { Clock, Pencil, Plus, Star } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { AssigneePicker } from "./AssigneePicker";
import { NoteCard } from "./NoteCard";
import { TabHeader } from "./TabHeader";
import { WeatherChip } from "./WeatherChip";
import { ACTIVE_MEMBERS, MOCK_NOTES } from "./mock-data";
import type { Note } from "./types";

export function NotesView() {
  const [notes, setNotes] = useState<Note[]>(MOCK_NOTES);
  const [selected, setSelected] = useState<
    { kind: "member"; id: string } | { kind: "family-wide" }
  >({ kind: "family-wide" });
  const [quickInput, setQuickInput] = useState("");

  const pinned = notes.filter((n) => n.pinned);
  const recent = notes.filter((n) => !n.pinned);

  const handleQuickAdd = () => {
    const text = quickInput.trim();
    if (!text) return;
    const id = `n_${Date.now()}`;
    const newNote: Note = {
      id,
      title: text,
      labels: [],
      pinned: false,
      assignee: selected,
    };
    setNotes((prev) => [newNote, ...prev]);
    setQuickInput("");
  };

  const handleToggleChecklist = (noteId: string, itemIndex: number) => {
    setNotes((prev) =>
      prev.map((n) => {
        if (n.id !== noteId || !n.checklist) return n;
        const nextChecklist = n.checklist.map((it, i) =>
          i === itemIndex ? { ...it, done: !it.done } : it,
        );
        return { ...n, checklist: nextChecklist };
      }),
    );
  };

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-notes"
      aria-labelledby="tab-notes"
    >
      <TabHeader
        eyebrow="Fridge Board"
        title="Good afternoon — what's on the fridge?"
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
            placeholder="Add a note — milk, permission slip, trash tomorrow…"
            value={quickInput}
            onChange={(e) => setQuickInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleQuickAdd();
            }}
            aria-label="Quick-add a note"
          />
          <AssigneePicker
            members={ACTIVE_MEMBERS}
            selected={selected}
            onSelect={setSelected}
          />
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimaryCompact}`}
            onClick={handleQuickAdd}
          >
            <Plus size={18} strokeWidth={2.4} />
            Add
          </button>
        </div>

        <NotesSection
          title="Pinned"
          count={pinned.length}
          icon={<Star size={14} fill="currentColor" strokeWidth={0} />}
        >
          {pinned.length === 0 ? (
            <EmptyNotes label="No pinned notes yet." />
          ) : (
            <div className={styles.notesGrid}>
              {pinned.map((n, i) => (
                <NoteCard
                  key={n.id}
                  note={n}
                  cardIndex={i}
                  onToggleChecklist={handleToggleChecklist}
                />
              ))}
            </div>
          )}
        </NotesSection>

        <NotesSection
          title="Recent"
          count={recent.length}
          icon={<Clock size={14} strokeWidth={2.5} />}
        >
          <div className={styles.notesGrid}>
            {recent.map((n, i) => (
              <NoteCard
                key={n.id}
                note={n}
                cardIndex={i}
                onToggleChecklist={handleToggleChecklist}
              />
            ))}
            <button type="button" className={styles.addNoteCard}>
              <span className={styles.addNotePlus} aria-hidden="true">
                <Plus size={22} strokeWidth={2.4} />
              </span>
              <div>New note</div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>Or ask the assistant</div>
            </button>
          </div>
        </NotesSection>
      </div>
    </section>
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
      <div className={styles.sectionLabel}>
        <span aria-hidden="true">{icon}</span>
        {title}
        <span className={styles.sectionCount}>{count}</span>
        <div className={styles.sectionDivider} />
      </div>
      {children}
    </>
  );
}

function EmptyNotes({ label }: { label: string }) {
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
