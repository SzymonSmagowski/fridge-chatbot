"use client";
import { House, Plus } from "lucide-react";
import styles from "./fridge.module.css";
import { initialsFromName } from "./types";
import type { MemberResponse } from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export type AssigneeSelection =
  | { kind: "member"; id: string }
  | { kind: "family-wide" };

export interface AssigneePickerProps {
  members: MemberResponse[];
  selected: AssigneeSelection;
  onSelect: (next: AssigneeSelection) => void;
  onOpenMore?: () => void;
  allowFamilyWide?: boolean;
  maxVisible?: number;
}

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

  const isMemberSelected = (m: MemberResponse) =>
    selected.kind === "member" && selected.id === m.id;
  const isFamilyWideSelected = selected.kind === "family-wide";

  return (
    <div
      className={styles.assigneePicker}
      role="radiogroup"
      aria-label={m.assignee_picker_label()}
    >
      {allowFamilyWide ? (
        <button
          type="button"
          role="radio"
          aria-checked={isFamilyWideSelected}
          aria-label={m.assignee_picker_family_wide_aria()}
          title={m.assignee_picker_family_wide_title()}
          className={`${styles.pickerAvatar} ${isFamilyWideSelected ? styles.selected : ""}`}
          style={{ background: "var(--muted)", color: "var(--muted-fg)" }}
          onClick={() => onSelect({ kind: "family-wide" })}
        >
          <House size={16} strokeWidth={2} />
        </button>
      ) : null}
      {visible.map((mem) => (
        <button
          key={mem.id}
          type="button"
          role="radio"
          aria-checked={isMemberSelected(mem)}
          aria-label={m.assignee_picker_member_aria({ name: mem.name })}
          title={mem.name}
          className={`${styles.pickerAvatar} ${isMemberSelected(mem) ? styles.selected : ""}`}
          style={{ background: `var(--member-${mem.color})` }}
          onClick={() => onSelect({ kind: "member", id: mem.id })}
        >
          {initialsFromName(mem.name)}
        </button>
      ))}
      {hiddenCount > 0 && onOpenMore ? (
        <button
          type="button"
          className={styles.pickerAvatar}
          aria-label={m.assignee_picker_more_aria({ count: hiddenCount })}
          style={{ background: "var(--muted)", color: "var(--muted-fg)", fontSize: 16 }}
          onClick={onOpenMore}
        >
          <Plus size={16} strokeWidth={2.4} />
        </button>
      ) : null}
    </div>
  );
}
