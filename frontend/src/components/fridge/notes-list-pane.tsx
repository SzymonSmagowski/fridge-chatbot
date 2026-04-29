"use client";
import { Pin, Plus, ShoppingCart } from "lucide-react";
import styles from "./fridge.module.css";
import { previewLine, splitTitleAndBody } from "./notes-content";
import { formatRelative } from "./use-relative-time";
import { SHOPPING_LIST_SLUG, type NoteResponse } from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export interface NotesListPaneProps {
  notes: NoteResponse[];
  selectedId: string | null;
  hasShoppingList: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onCreateShoppingList: () => void;
}

export function NotesListPane({
  notes,
  selectedId,
  hasShoppingList,
  onSelect,
  onCreate,
  onCreateShoppingList,
}: NotesListPaneProps) {
  const shopping = notes.find((n) =>
    n.labels.some((l) => l.slug === SHOPPING_LIST_SLUG),
  );
  const others = notes
    .filter((n) => n !== shopping)
    .slice()
    .sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );

  return (
    <nav className={styles.notesListPane} aria-label={m.notes_list_aria()}>
      <div className={styles.notesListHeader}>
        <span className={styles.notesListTitle}>{m.notes_list_title()}</span>
        <button
          type="button"
          className={styles.notesListAddBtn}
          onClick={onCreate}
          aria-label={m.notes_list_add_aria()}
        >
          <Plus size={20} strokeWidth={2.4} />
        </button>
      </div>

      <ul className={styles.notesListItems} role="list">
        {!hasShoppingList ? (
          <li>
            <button
              type="button"
              className={styles.notesListShoppingCta}
              onClick={onCreateShoppingList}
            >
              <ShoppingCart size={16} strokeWidth={2} />
              {m.notes_create_shopping_list()}
            </button>
          </li>
        ) : null}

        {shopping ? (
          <li>
            <NotesListItem
              note={shopping}
              isActive={shopping.id === selectedId}
              isPinned
              onSelect={onSelect}
            />
            {others.length > 0 ? (
              <div className={styles.notesListSeparator} aria-hidden="true" />
            ) : null}
          </li>
        ) : null}

        {others.length === 0 && hasShoppingList ? null : others.length === 0 ? (
          <li className={styles.notesListEmpty}>{m.notes_list_empty()}</li>
        ) : (
          others.map((note) => (
            <li key={note.id}>
              <NotesListItem
                note={note}
                isActive={note.id === selectedId}
                isPinned={false}
                onSelect={onSelect}
              />
            </li>
          ))
        )}
      </ul>
    </nav>
  );
}

interface ItemProps {
  note: NoteResponse;
  isActive: boolean;
  isPinned: boolean;
  onSelect: (id: string) => void;
}

function NotesListItem({ note, isActive, isPinned, onSelect }: ItemProps) {
  const isShopping = note.labels.some((l) => l.slug === SHOPPING_LIST_SLUG);
  const { title, body } = splitTitleAndBody(note.content);
  const displayTitle = isShopping
    ? m.notes_shopping_list_title()
    : title || m.notes_list_untitled();
  const preview = isShopping ? "" : previewLine(body);

  return (
    <button
      type="button"
      className={`${styles.notesListItem} ${isActive ? styles.notesListItemActive : ""}`}
      onClick={() => onSelect(note.id)}
      aria-current={isActive ? "page" : undefined}
    >
      <div className={styles.notesListItemHead}>
        {isPinned ? (
          <Pin
            className={styles.notesListItemPin}
            size={12}
            fill="currentColor"
            strokeWidth={0}
            aria-hidden="true"
          />
        ) : null}
        <span className={styles.notesListItemTitle}>{displayTitle}</span>
      </div>
      {preview ? (
        <span className={styles.notesListItemPreview}>{preview}</span>
      ) : null}
      <span className={styles.notesListItemTime}>
        {formatRelative(note.updated_at)}
      </span>
    </button>
  );
}
