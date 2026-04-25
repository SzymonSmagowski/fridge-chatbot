"use client";
import { Car as CarIcon } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { Sheet } from "./Sheet";
import { MEMBER_COLOR_HEX, type Car, type MemberColor } from "./types";

const PALETTE: MemberColor[] = [
  "sage",
  "blue",
  "blush",
  "butter",
  "stone",
  "lavender",
  "seafoam",
];

export interface AddCarSheetProps {
  state: { mode: "create" } | { mode: "edit"; car: Car } | null;
  onClose: () => void;
  onSave: (car: Car) => void;
}

export function AddCarSheet({ state, onClose, onSave }: AddCarSheetProps) {
  const open = state !== null;
  const editing = state?.mode === "edit" ? state.car : null;
  const key = editing?.id ?? (open ? "create" : "closed");

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${editing.name}` : "Add a car"}
    >
      <CarForm key={key} editing={editing} onSave={onSave} onCancel={onClose} />
    </Sheet>
  );
}

function CarForm({
  editing,
  onSave,
  onCancel,
}: {
  editing: Car | null;
  onSave: (c: Car) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? "");
  const [year, setYear] = useState(editing?.year?.toString() ?? "");
  const [colorLabel, setColorLabel] = useState(editing?.colorLabel ?? "");
  const [notes, setNotes] = useState(editing?.notes ?? "");
  const [color, setColor] = useState<MemberColor>(editing?.color ?? "stone");

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const car: Car = {
      id: editing?.id ?? `c_${Date.now()}`,
      name: trimmed,
      year: year ? Number(year) : undefined,
      colorLabel: colorLabel.trim() || undefined,
      notes: notes.trim() || undefined,
      color,
      status: editing?.status ?? "active",
    };
    onSave(car);
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
          <label className={styles.fieldLabel} htmlFor="c-color">Color</label>
          <input
            id="c-color"
            className={styles.input}
            value={colorLabel}
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
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="At Pete's Garage"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Chip color</label>
        <div className={styles.colorChoiceRow} role="radiogroup" aria-label="Pick a chip color">
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
          Save car
        </button>
      </div>
    </>
  );
}
