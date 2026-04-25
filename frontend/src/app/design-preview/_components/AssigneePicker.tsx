"use client";
import { House, Plus } from "lucide-react";
import styles from "../preview.module.css";
import type { Member } from "./types";

type SelectedValue = { kind: "member"; id: string } | { kind: "family-wide" };

export interface AssigneePickerProps {
  members: Member[];
  selected: SelectedValue;
  onSelect: (next: SelectedValue) => void;
  onOpenMore?: () => void;
  /** Whether to show the Family-wide sentinel as the first option. */
  allowFamilyWide?: boolean;
  maxVisible?: number;
}

/**
 * Compact horizontal pill picker. A single selection can be either a member
 * (by id) or the special "family-wide" sentinel. The trailing + opens a sheet
 * with the full member list (for families >4 active members).
 */
export function AssigneePicker({
  members,
  selected,
  onSelect,
  onOpenMore,
  allowFamilyWide = true,
  maxVisible = 4,
}: AssigneePickerProps) {
  const active = members.filter((m) => m.status === "active");
  const visible = active.slice(0, maxVisible);
  const hiddenCount = active.length - visible.length;

  const isMemberSelected = (m: Member) => selected.kind === "member" && selected.id === m.id;
  const isFamilyWideSelected = selected.kind === "family-wide";

  return (
    <div
      className={styles.assigneePicker}
      role="radiogroup"
      aria-label="Assign to a family member"
    >
      {allowFamilyWide ? (
        <button
          type="button"
          role="radio"
          aria-checked={isFamilyWideSelected}
          aria-label="Assign to the whole family"
          title="Family-wide"
          className={`${styles.pickerAvatar} ${isFamilyWideSelected ? styles.selected : ""}`}
          style={{ background: "var(--muted)", color: "var(--muted-fg)" }}
          onClick={() => onSelect({ kind: "family-wide" })}
        >
          <House size={16} strokeWidth={2} />
        </button>
      ) : null}
      {visible.map((m) => (
        <button
          key={m.id}
          type="button"
          role="radio"
          aria-checked={isMemberSelected(m)}
          aria-label={`Assign to ${m.name}`}
          title={m.name}
          className={`${styles.pickerAvatar} ${isMemberSelected(m) ? styles.selected : ""}`}
          style={{ background: `var(--member-${m.color})` }}
          onClick={() => onSelect({ kind: "member", id: m.id })}
        >
          {m.initials}
        </button>
      ))}
      {hiddenCount > 0 && onOpenMore ? (
        <button
          type="button"
          className={styles.pickerAvatar}
          aria-label={`Show ${hiddenCount} more members`}
          style={{ background: "var(--muted)", color: "var(--muted-fg)", fontSize: 16 }}
          onClick={onOpenMore}
        >
          <Plus size={16} strokeWidth={2.4} />
        </button>
      ) : null}
    </div>
  );
}
