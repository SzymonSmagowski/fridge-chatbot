"use client";
import { ChevronDown, ChevronUp, Pin, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import styles from "./fridge.module.css";
import { AssigneePicker, type AssigneeSelection } from "./assignee-picker";
import { joinTitleAndBody, splitTitleAndBody } from "./notes-content";
import { ShoppingListEditor } from "./shopping-list-editor";
import {
  SHOPPING_LIST_SLUG,
  type CarResponse,
  type MemberResponse,
  type NoteResponse,
} from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export interface NoteEditorPaneProps {
  note: NoteResponse;
  members: MemberResponse[];
  cars: CarResponse[];
  isJustCreated: boolean;
  onChange: (next: { title: string; body: string }) => void;
  onAssigneeChange: (next: AssigneeSelection) => void;
  onCarToggle: (carId: string) => void;
  onDelete: () => void;
}

export function NoteEditorPane({
  note,
  members,
  cars,
  isJustCreated,
  onChange,
  onAssigneeChange,
  onCarToggle,
  onDelete,
}: NoteEditorPaneProps) {
  const initial = splitTitleAndBody(note.content);
  const [title, setTitle] = useState(initial.title);
  const [body, setBody] = useState(initial.body);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const titleRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const lastNoteIdRef = useRef(note.id);

  // Switching notes: reset local state, focus appropriately.
  useEffect(() => {
    if (note.id !== lastNoteIdRef.current) {
      const fresh = splitTitleAndBody(note.content);
      setTitle(fresh.title);
      setBody(fresh.body);
      setDetailsOpen(false);
      lastNoteIdRef.current = note.id;
    }
  }, [note.id, note.content]);

  // Brand-new note: focus the title input.
  useEffect(() => {
    if (isJustCreated) titleRef.current?.focus();
  }, [isJustCreated, note.id]);

  // Server pushed an external update for the open note (family-events WS).
  // Only adopt it when the user isn't actively editing the same field.
  useEffect(() => {
    const fresh = splitTitleAndBody(note.content);
    const currentJoined = joinTitleAndBody({ title, body });
    if (currentJoined === note.content) return;
    const focused = document.activeElement;
    const userEditingTitle = focused === titleRef.current;
    const userEditingBody = focused === bodyRef.current;
    if (!userEditingTitle && fresh.title !== title) setTitle(fresh.title);
    if (!userEditingBody && fresh.body !== body) setBody(fresh.body);
    // We deliberately depend only on note.content + id — local state changes
    // are driven by the user via the input handlers and shouldn't re-trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note.id, note.content]);

  const isShopping = note.labels.some((l) => l.slug === SHOPPING_LIST_SLUG);

  const setTitleField = (v: string) => {
    setTitle(v);
    onChange({ title: v, body });
  };
  const setBodyField = (v: string) => {
    setBody(v);
    onChange({ title, body: v });
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      bodyRef.current?.focus();
    }
  };

  const assignee: AssigneeSelection = note.assignee_member_id
    ? { kind: "member", id: note.assignee_member_id }
    : { kind: "family-wide" };

  return (
    <div className={styles.noteEditor}>
      <div className={styles.noteEditorHead}>
        {isShopping ? (
          <span className={styles.editorPinTag} aria-label={m.notes_pinned_aria()}>
            <Pin size={14} fill="currentColor" strokeWidth={0} />
            {m.notes_shopping_list_title()}
          </span>
        ) : null}
        <div className={styles.noteEditorAssignee}>
          <AssigneePicker
            members={members}
            selected={assignee}
            onSelect={onAssigneeChange}
          />
        </div>
        <button
          type="button"
          className={styles.editorDeleteBtn}
          onClick={onDelete}
          aria-label={m.notes_editor_delete_aria()}
          title={m.notes_editor_delete_aria()}
          disabled={isShopping}
        >
          <Trash2 size={18} strokeWidth={2} />
        </button>
      </div>

      {isShopping ? (
        <ShoppingListEditor
          content={note.content}
          onChange={(raw) => onChange({ title: "", body: raw })}
        />
      ) : (
        <>
          <input
            ref={titleRef}
            className={styles.noteEditorTitle}
            value={title}
            onChange={(e) => setTitleField(e.target.value)}
            onKeyDown={handleTitleKeyDown}
            placeholder={m.notes_editor_title_placeholder()}
            aria-label={m.notes_editor_title_aria()}
          />

          <textarea
            ref={bodyRef}
            className={styles.noteEditorBody}
            value={body}
            onChange={(e) => setBodyField(e.target.value)}
            placeholder={m.notes_editor_body_placeholder()}
            aria-label={m.notes_editor_body_aria()}
          />
        </>
      )}

      {cars.length > 0 ? (
        <div className={styles.noteEditorDetails}>
          <button
            type="button"
            className={styles.noteEditorDetailsToggle}
            onClick={() => setDetailsOpen((v) => !v)}
            aria-expanded={detailsOpen}
          >
            {detailsOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            {m.notes_editor_cars_label()}
          </button>
          {detailsOpen ? (
            <div className={styles.noteEditorDetailsBody}>
              <div className={styles.carChipRow}>
                {cars.map((car) => {
                  const selected = note.car_ids.includes(car.id);
                  return (
                    <button
                      key={car.id}
                      type="button"
                      className={`${styles.carChip} ${selected ? styles.carChipSelected : ""}`}
                      onClick={() => onCarToggle(car.id)}
                      aria-pressed={selected}
                    >
                      {String.fromCodePoint(0x1f697)} {car.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
