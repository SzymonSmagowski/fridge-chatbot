"use client";
import styles from "./fridge.module.css";
import { previewLine, splitTitleAndBody } from "./notes-content";
import { formatRelative } from "./use-relative-time";
import { SHOPPING_LIST_SLUG, type NoteResponse } from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export interface NotesHeroStripProps {
  notes: NoteResponse[];
  selectedId: string | null;
  onOpen: (id: string) => void;
}

export function NotesHeroStrip({ notes, selectedId, onOpen }: NotesHeroStripProps) {
  if (notes.length === 0) return null;
  return (
    <div className={styles.notesHero} aria-label={m.notes_hero_aria()}>
      <div className={styles.notesHeroLabel}>{m.notes_hero_label()}</div>
      <div className={styles.notesHeroCards}>
        {notes.map((note, i) => (
          <HeroCard
            key={note.id}
            note={note}
            isActive={note.id === selectedId}
            cardIndex={i}
            onOpen={onOpen}
          />
        ))}
      </div>
    </div>
  );
}

interface HeroCardProps {
  note: NoteResponse;
  isActive: boolean;
  cardIndex: number;
  onOpen: (id: string) => void;
}

function HeroCard({ note, isActive, cardIndex, onOpen }: HeroCardProps) {
  const isShopping = note.labels.some((l) => l.slug === SHOPPING_LIST_SLUG);
  const { title, body } = splitTitleAndBody(note.content);
  const displayTitle = isShopping
    ? m.notes_shopping_list_title()
    : title || m.notes_list_untitled();
  const preview = isShopping
    ? m.notes_hero_shopping_hint()
    : previewLine(body, 90);

  return (
    <button
      type="button"
      className={`${styles.notesHeroCard} ${isActive ? styles.notesHeroCardActive : ""}`}
      style={{ ["--card-i" as string]: String(cardIndex) }}
      onClick={() => onOpen(note.id)}
    >
      <div className={styles.notesHeroCardTitle}>{displayTitle}</div>
      {preview ? (
        <div className={styles.notesHeroCardPreview}>{preview}</div>
      ) : null}
      <div className={styles.notesHeroCardTime}>
        {formatRelative(note.updated_at)}
      </div>
    </button>
  );
}
