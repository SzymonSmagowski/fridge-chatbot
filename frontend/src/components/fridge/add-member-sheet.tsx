"use client";
import { LogIn } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { ConnectGoogleModal } from "./connect-google-modal";
import { FridgeSheet } from "./sheet";
import { initialsFromName, MEMBER_COLOR_HEX, MEMBER_COLORS, type MemberColor } from "./types";
import { ApiError, membersApi, type MemberResponse } from "@/lib/api";

export interface AddMemberSheetProps {
  state: { mode: "create" } | { mode: "edit"; member: MemberResponse } | null;
  onClose: () => void;
  onSaved: () => void;
}

export function AddMemberSheet({ state, onClose, onSaved }: AddMemberSheetProps) {
  const open = state !== null;
  const editing = state?.mode === "edit" ? state.member : null;
  const key = editing?.id ?? (open ? "create" : "closed");

  return (
    <FridgeSheet
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${editing.name}` : "Add a family member"}
    >
      <MemberForm key={key} editing={editing} onSaved={onSaved} onCancel={onClose} />
    </FridgeSheet>
  );
}

function MemberForm({
  editing,
  onSaved,
  onCancel,
}: {
  editing: MemberResponse | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? "");
  const [nickname, setNickname] = useState(editing?.nickname ?? "");
  const [color, setColor] = useState<MemberColor>(editing?.color ?? "sage");
  const [submitting, setSubmitting] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const onConnectModalClose = useCallback(() => setConnectOpen(false), []);

  const initials = initialsFromName(name);

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    try {
      if (editing) {
        await membersApi.update(editing.id, {
          name: trimmed,
          nickname: nickname.trim() || null,
          color,
        });
      } else {
        await membersApi.create({
          name: trimmed,
          nickname: nickname.trim() || null,
          color,
        });
      }
      onSaved();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to save member";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const connectGoogle = () => {
    if (!editing) {
      toast.message("Save the member first to connect Google.");
      return;
    }
    setConnectOpen(true);
  };

  const googleStatus = editing?.google.status;

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
          value={nickname ?? ""}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="Mom"
          autoComplete="off"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Color</label>
        <div className={styles.colorChoiceRow} role="radiogroup" aria-label="Pick a color">
          {MEMBER_COLORS.map((c) => (
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

      {editing ? (
        <div className={styles.field}>
          <label className={styles.fieldLabel}>Google Calendar</label>
          {googleStatus === "connected" ? (
            <div
              style={{
                padding: "10px 12px",
                background: "var(--surface-raised)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--fridge-radius)",
                fontSize: 14,
                color: "var(--muted-fg)",
              }}
            >
              Connected as {editing.google.email ?? "Google account"}.
            </div>
          ) : (
            <>
              <button
                type="button"
                className={styles.btn}
                style={{ width: "fit-content" }}
                onClick={connectGoogle}
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
      ) : null}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: "auto", paddingTop: 12 }}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
          onClick={onCancel}
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={() => void save()}
          disabled={!name.trim() || submitting}
        >
          Save member
        </button>
      </div>

      <ConnectGoogleModal
        open={connectOpen}
        memberId={editing?.id ?? null}
        memberName={editing?.name ?? null}
        onClose={onConnectModalClose}
      />
    </>
  );
}
