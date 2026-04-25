"use client";
import { Plus } from "lucide-react";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

export interface AddNoteCardProps {
  onClick?: () => void;
  label?: string;
  hint?: string;
}

export function AddNoteCard({
  onClick,
  label,
  hint,
}: AddNoteCardProps) {
  return (
    <button type="button" className={styles.addNoteCard} onClick={onClick}>
      <span className={styles.addNotePlus} aria-hidden="true">
        <Plus size={22} strokeWidth={2.4} />
      </span>
      <div>{label ?? m.notes_add_card_label()}</div>
      <div style={{ fontSize: 13, fontWeight: 500 }}>{hint ?? m.notes_add_card_hint()}</div>
    </button>
  );
}
