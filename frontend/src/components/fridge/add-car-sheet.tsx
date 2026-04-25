"use client";
import { Car as CarIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { FridgeSheet } from "./sheet";
import { MEMBER_COLOR_HEX, MEMBER_COLORS, type MemberColor } from "./types";
import { ApiError, carsApi, type CarResponse } from "@/lib/api";

export interface AddCarSheetProps {
  state: { mode: "create" } | { mode: "edit"; car: CarResponse } | null;
  onClose: () => void;
  onSaved: () => void;
}

export function AddCarSheet({ state, onClose, onSaved }: AddCarSheetProps) {
  const open = state !== null;
  const editing = state?.mode === "edit" ? state.car : null;
  const key = editing?.id ?? (open ? "create" : "closed");

  return (
    <FridgeSheet
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${editing.name}` : "Add a car"}
    >
      <CarForm key={key} editing={editing} onSaved={onSaved} onCancel={onClose} />
    </FridgeSheet>
  );
}

function CarForm({
  editing,
  onSaved,
  onCancel,
}: {
  editing: CarResponse | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? "");
  const [year, setYear] = useState(editing?.year?.toString() ?? "");
  const [colorLabel, setColorLabel] = useState(editing?.color_label ?? "");
  const [notes, setNotes] = useState(editing?.notes ?? "");
  const [color, setColor] = useState<MemberColor>(editing?.color ?? "stone");
  const [submitting, setSubmitting] = useState(false);

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    try {
      const body = {
        name: trimmed,
        year: year ? Number(year) : null,
        color_label: colorLabel.trim() || null,
        notes: notes.trim() || null,
        color,
      };
      if (editing) {
        await carsApi.update(editing.id, body);
      } else {
        await carsApi.create(body);
      }
      onSaved();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to save car";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div
        className={styles.previewCrest}
        style={{ background: MEMBER_COLOR_HEX[color] }}
        aria-hidden="true"
      >
        <CarIcon size={32} strokeWidth={2} />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="c-name">Name (required)</label>
        <input
          id="c-name"
          className={styles.input}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Family Volvo"
          autoFocus
          autoComplete="off"
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="c-year">Year</label>
          <input
            id="c-year"
            className={styles.input}
            value={year}
            onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))}
            placeholder="2019"
            inputMode="numeric"
          />
        </div>
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="c-color">Color label</label>
          <input
            id="c-color"
            className={styles.input}
            value={colorLabel ?? ""}
            onChange={(e) => setColorLabel(e.target.value)}
            placeholder="White"
          />
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="c-notes">Notes (optional)</label>
        <input
          id="c-notes"
          className={styles.input}
          value={notes ?? ""}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="At Pete's Garage"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Chip color</label>
        <div className={styles.colorChoiceRow} role="radiogroup" aria-label="Pick a chip color">
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
          Save car
        </button>
      </div>
    </>
  );
}
