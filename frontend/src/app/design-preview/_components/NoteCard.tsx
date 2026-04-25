"use client";
import { Link2, Pin } from "lucide-react";
import { useMemo } from "react";
import styles from "../preview.module.css";
import { CarAvatar } from "./CarAvatar";
import { MemberAvatar } from "./MemberAvatar";
import { renderNoteIcon } from "./icons";
import { getCar, getMember } from "./mock-data";
import { NOTE_ASSIGNED_CLASS, type Note } from "./types";

export interface NoteCardProps {
  note: Note;
  cardIndex?: number;
  onClick?: (noteId: string) => void;
  onToggleChecklist?: (noteId: string, itemIndex: number) => void;
}

export function NoteCard({ note, cardIndex = 0, onClick, onToggleChecklist }: NoteCardProps) {
  const iconEl = renderNoteIcon(note.icon, 18);

  const assignee = useMemo(() => {
    if (!note.assignee || note.assignee.kind === "family-wide")
      return { label: "Family-wide" as const };
    if (note.assignee.kind === "member") {
      const m = getMember(note.assignee.id);
      if (!m) return { label: "Unassigned" as const };
      return { label: m.name, kind: "member" as const, member: m };
    }
    const c = getCar(note.assignee.id);
    if (!c) return { label: "Unassigned" as const };
    return { label: c.name, kind: "car" as const, car: c };
  }, [note.assignee]);

  const assignedClass = useMemo(() => {
    if (!note.assignee || note.assignee.kind === "family-wide") return "";
    if (note.assignee.kind === "member") {
      const m = getMember(note.assignee.id);
      return m ? styles[NOTE_ASSIGNED_CLASS[m.color]] : "";
    }
    const c = getCar(note.assignee.id);
    return c ? styles[NOTE_ASSIGNED_CLASS[c.color]] : "";
  }, [note.assignee]);

  const isWhite = !assignedClass;
  const noteClasses = [
    styles.note,
    assignedClass,
    isWhite ? styles.noteWhite : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={noteClasses}
      style={{
        gridColumn: note.span === 2 ? "span 2" : undefined,
        // Staggered entrance animation index
        ["--card-i" as string]: String(cardIndex),
      }}
      onClick={onClick ? () => onClick(note.id) : undefined}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className={styles.noteTop}>
        <div className={styles.noteLeft}>
          {iconEl ? (
            <span className={styles.noteIcon} aria-hidden="true">
              {iconEl}
            </span>
          ) : null}
          {note.title ? <div className={styles.noteTitle}>{note.title}</div> : null}
        </div>
        {note.pinned ? (
          <span className={styles.notePin} aria-label="Pinned">
            <Pin size={16} fill="currentColor" strokeWidth={0} />
          </span>
        ) : null}
      </div>

      {note.checklist ? (
        <ul className={styles.shoppingList}>
          {note.checklist.map((item, i) => (
            <li
              key={`${item.text}-${i}`}
              className={item.done ? styles.done : ""}
              onClick={(e) => {
                e.stopPropagation();
                onToggleChecklist?.(note.id, i);
              }}
              role="checkbox"
              aria-checked={item.done}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === " " || e.key === "Enter") {
                  e.preventDefault();
                  onToggleChecklist?.(note.id, i);
                }
              }}
            >
              {item.text}
            </li>
          ))}
        </ul>
      ) : note.body ? (
        <div className={styles.noteBody}>{note.body}</div>
      ) : null}

      <div className={styles.noteFooter}>
        <div className={styles.labels}>
          {note.linkedEventId ? (
            <span className={styles.label} title="Linked to a calendar event">
              <Link2 size={10} strokeWidth={2.4} style={{ marginRight: 4, verticalAlign: -1 }} />
              Recurring event
            </span>
          ) : null}
          {note.labels.map((l) => (
            <span key={l} className={styles.label}>
              {l}
            </span>
          ))}
          {note.carLabels?.map((cid) => {
            const car = getCar(cid);
            if (!car) return null;
            return (
              <span key={cid} className={styles.label}>
                🚗 {car.name}
              </span>
            );
          })}
        </div>
        <div className={styles.noteAssignee}>
          {assignee.label === "Family-wide" || assignee.label === "Unassigned" ? (
            <span>{assignee.label}</span>
          ) : assignee.kind === "member" && assignee.member ? (
            <>
              <MemberAvatar
                initials={assignee.member.initials}
                color={assignee.member.color}
                size="sm"
              />
              <span>{assignee.member.nickname ?? assignee.member.name}</span>
            </>
          ) : assignee.kind === "car" && assignee.car ? (
            <>
              <CarAvatar color={assignee.car.color} size="sm" />
              <span>{assignee.car.name}</span>
            </>
          ) : null}
        </div>
      </div>
    </article>
  );
}
