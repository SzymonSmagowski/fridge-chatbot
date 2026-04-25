"use client";
import { LogIn } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { Sheet } from "./Sheet";
import { MEMBER_COLOR_HEX, type GoogleConnectionState, type Member, type MemberColor } from "./types";

const PALETTE: MemberColor[] = [
  "sage",
  "blue",
  "blush",
  "butter",
  "stone",
  "lavender",
  "seafoam",
];

export interface AddMemberSheetProps {
  state: { mode: "create" } | { mode: "edit"; member: Member } | null;
  onClose: () => void;
  onSave: (member: Member) => void;
}

/**
 * Outer component owns the Sheet open/close. The inner <MemberForm /> is keyed
 * on the editing id so each new edit flow gets its own fresh useState, which
 * sidesteps the react-hooks/set-state-in-effect lint (no effect-driven mirror
 * of props into state).
 */
export function AddMemberSheet({ state, onClose, onSave }: AddMemberSheetProps) {
  const open = state !== null;
  const editing = state?.mode === "edit" ? state.member : null;
  const key = editing?.id ?? (open ? "create" : "closed");

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${editing.name}` : "Add a family member"}
    >
      <MemberForm key={key} editing={editing} onSave={onSave} onCancel={onClose} />
    </Sheet>
  );
}

function MemberForm({
  editing,
  onSave,
  onCancel,
}: {
  editing: Member | null;
  onSave: (m: Member) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? "");
  const [nickname, setNickname] = useState(editing?.nickname ?? "");
  const [color, setColor] = useState<MemberColor>(editing?.color ?? "sage");
  const [google, setGoogle] = useState<GoogleConnectionState>(editing?.google ?? "pending");

  const initials =
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join("") || "??";

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const member: Member = {
      id: editing?.id ?? `m_${Date.now()}`,
      name: trimmed,
      nickname: nickname.trim() || undefined,
      initials,
      color,
      google,
      email: editing?.email,
      status: editing?.status ?? "active",
      isSetupOwner: editing?.isSetupOwner,
    };
    onSave(member);
  };

  return (
    <>
      <div
        className={styles.previewCrest}
        style={{ background: MEMBER_COLOR_HEX[color] }}
        aria-hidden="true"
      >
        {initials}
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="m-name">Name (required)</label>
        <input
          id="m-name"
          className={styles.input}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Monika"
          autoComplete="off"
          autoFocus
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="m-nick">Nickname (optional)</label>
        <input
          id="m-nick"
          className={styles.input}
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="Mom"
          autoComplete="off"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Color</label>
        <div className={styles.colorChoiceRow} role="radiogroup" aria-label="Pick a color">
          {PALETTE.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={color === c}
              aria-label={c}
              onClick={() => setColor(c)}
              className={`${styles.colorChoice} ${color === c ? styles.selected : ""}`}
              style={{ background: MEMBER_COLOR_HEX[c] }}
            />
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Google Calendar</label>
        {google === "connected" ? (
          <div
            style={{
              padding: "10px 12px",
              background: "var(--surface-raised)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius)",
              fontSize: 14,
              color: "var(--muted-fg)",
            }}
          >
            Connected. Events assigned to this member will sync to their primary calendar.
            <button
              type="button"
              className={`${styles.btn} ${styles.btnSmall} ${styles.btnGhost}`}
              style={{ marginLeft: 8 }}
              onClick={() => setGoogle("pending")}
            >
              Disconnect
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              className={styles.btn}
              style={{ width: "fit-content" }}
              onClick={() => setGoogle("connected")}
            >
              <LogIn size={16} strokeWidth={2.4} />
              Connect Google
            </button>
            <div style={{ fontSize: 13, color: "var(--muted-fg)", marginTop: 6 }}>
              Skip for now — you can connect later from this member&apos;s row.
            </div>
          </>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: "auto", paddingTop: 12 }}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={save}
          disabled={!name.trim()}
        >
          Save member
        </button>
      </div>
    </>
  );
}
