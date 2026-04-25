"use client";
import { Link2, Pin } from "lucide-react";
import { useMemo } from "react";
import styles from "./fridge.module.css";
import { CarAvatar } from "./car-avatar";
import { MemberAvatar } from "./member-avatar";
import { renderNoteIcon } from "./note-icon";
import { parseChecklist } from "./shopping-checklist";
import { initialsFromName, NOTE_ASSIGNED_CLASS } from "./types";
import { SHOPPING_LIST_SLUG, type CarResponse, type MemberResponse, type NoteResponse } from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export interface NoteCardProps {
  note: NoteResponse;
  members: MemberResponse[];
  cars: CarResponse[];
  cardIndex?: number;
  /** When set, the card spans 2 grid columns. */
  span?: 1 | 2;
  onClick?: (noteId: string) => void;
  onToggleChecklist?: (noteId: string, itemIndex: number) => void;
}

/**
 * Splits the (single-string) content into a heading line and the rest.
 * The Architect's contract has no separate `title` column — by convention the
 * first line is the heading, the rest is the body. Empty content shows nothing.
 */
function splitTitleAndBody(content: string): { title: string; body: string } {
  const trimmed = content.replace(/^\s+|\s+$/g, "");
  const newlineIdx = trimmed.indexOf("\n");
  if (newlineIdx === -1) return { title: trimmed, body: "" };
  return {
    title: trimmed.slice(0, newlineIdx).trim(),
    body: trimmed.slice(newlineIdx + 1).trim(),
  };
}

export function NoteCard({
  note,
  members,
  cars,
  cardIndex = 0,
  span,
  onClick,
  onToggleChecklist,
}: NoteCardProps) {
  const iconEl = renderNoteIcon(note.icon, 18);

  const isShoppingList = note.labels.some((l) => l.slug === SHOPPING_LIST_SLUG);
  const checklist = useMemo(
    () => (isShoppingList ? parseChecklist(note.content) : null),
    [isShoppingList, note.content],
  );

  const { title, body } = useMemo(() => {
    if (isShoppingList) return { title: m.notes_shopping_list_title(), body: "" };
    return splitTitleAndBody(note.content);
  }, [isShoppingList, note.content]);

  const assignee = useMemo(() => {
    if (!note.assignee_member_id) {
      // family-wide
      return { kind: "family-wide" as const };
    }
    const m = members.find((x) => x.id === note.assignee_member_id);
    if (!m) return { kind: "unknown" as const };
    return { kind: "member" as const, member: m };
  }, [members, note.assignee_member_id]);

  const noteCars = useMemo(
    () => note.car_ids.map((cid) => cars.find((c) => c.id === cid)).filter((c): c is CarResponse => !!c),
    [cars, note.car_ids],
  );

  const assignedClass = useMemo(() => {
    if (assignee.kind === "member") return styles[NOTE_ASSIGNED_CLASS[assignee.member.color]];
    if (noteCars.length > 0) return styles[NOTE_ASSIGNED_CLASS[noteCars[0].color]];
    return "";
  }, [assignee, noteCars]);

  const isWhite = !assignedClass;
  const noteClasses = [
    styles.note,
    assignedClass,
    isWhite ? styles.noteWhite : "",
  ]
    .filter(Boolean)
    .join(" ");

  const labelChips = note.labels.filter((l) => l.slug !== SHOPPING_LIST_SLUG);

  return (
    <article
      className={noteClasses}
      style={{
        gridColumn: span === 2 ? "span 2" : undefined,
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
          {title ? <div className={styles.noteTitle}>{title}</div> : null}
        </div>
        {note.pinned ? (
          <span className={styles.notePin} aria-label={m.notes_pinned_aria()}>
            <Pin size={16} fill="currentColor" strokeWidth={0} />
          </span>
        ) : null}
      </div>

      {checklist ? (
        <ul className={styles.shoppingList}>
          {checklist.map((item, i) => (
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
      ) : body ? (
        <div className={styles.noteBody}>{body}</div>
      ) : null}

      <div className={styles.noteFooter}>
        <div className={styles.labels}>
          {note.linked_event_id ? (
            <span className={styles.label} title={m.notes_recurring_event_title()}>
              <Link2 size={10} strokeWidth={2.4} style={{ marginRight: 4, verticalAlign: -1 }} />
              {m.notes_recurring_event_chip()}
            </span>
          ) : null}
          {labelChips.map((l) => (
            <span key={l.slug} className={styles.label}>
              #{l.display_name}
            </span>
          ))}
          {noteCars.map((car) => (
            <span key={car.id} className={styles.label}>
              {String.fromCodePoint(0x1f697)} {car.name}
            </span>
          ))}
        </div>
        <div className={styles.noteAssignee}>
          {assignee.kind === "family-wide" ? (
            <span>{m.notes_assignee_family_wide()}</span>
          ) : assignee.kind === "member" ? (
            <>
              <MemberAvatar
                initials={initialsFromName(assignee.member.name)}
                color={assignee.member.color}
                size="sm"
              />
              <span>{assignee.member.nickname ?? assignee.member.name}</span>
            </>
          ) : noteCars.length > 0 ? (
            <>
              <CarAvatar color={noteCars[0].color} size="sm" />
              <span>{noteCars[0].name}</span>
            </>
          ) : (
            <span>{m.common_unassigned()}</span>
          )}
        </div>
      </div>
    </article>
  );
}
