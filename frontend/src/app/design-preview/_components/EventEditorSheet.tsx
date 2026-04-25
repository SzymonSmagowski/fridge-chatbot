"use client";
import { AlertCircle } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { AssigneePicker } from "./AssigneePicker";
import { CarAvatar } from "./CarAvatar";
import { Sheet } from "./Sheet";
import { ACTIVE_MEMBERS, MOCK_CARS, getMember } from "./mock-data";
import type { CalendarEvent } from "./types";

export interface EventEditorSheetProps {
  open: boolean;
  event: CalendarEvent | null;
  onClose: () => void;
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export function EventEditorSheet({ open, event, onClose }: EventEditorSheetProps) {
  const key = event?.id ?? (open ? "new" : "closed");
  return (
    <Sheet open={open} onClose={onClose} title={event ? "Edit event" : "New event"}>
      <EventForm key={key} event={event} onClose={onClose} />
    </Sheet>
  );
}

function EventForm({
  event,
  onClose,
}: {
  event: CalendarEvent | null;
  onClose: () => void;
}) {
  const isNew = !event;
  const initialStart = event?.startAt ?? new Date();
  const initialEnd =
    event?.endAt ?? new Date(initialStart.getTime() + 60 * 60 * 1000);
  const initialAssignee: { kind: "member"; id: string } | { kind: "family-wide" } =
    (() => {
      const firstMember = event?.assignees.find((a) => a.kind === "member");
      if (firstMember && firstMember.kind === "member") {
        return { kind: "member", id: firstMember.id };
      }
      return { kind: "family-wide" };
    })();
  const initialCars = (event?.assignees ?? [])
    .filter((a) => a.kind === "car")
    .map((a) => (a.kind === "car" ? a.id : ""))
    .filter(Boolean);

  const [title, setTitle] = useState(event?.title ?? "");
  const [start, setStart] = useState(toLocalInputValue(initialStart));
  const [end, setEnd] = useState(toLocalInputValue(initialEnd));
  const [location, setLocation] = useState(event?.location ?? "");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState(initialAssignee);
  const [selectedCars, setSelectedCars] = useState<string[]>(initialCars);
  const [showRecurrence, setShowRecurrence] = useState(
    Boolean(event?.rrule || event?.rruleLabel),
  );
  const [rruleFreq, setRruleFreq] = useState<"daily" | "weekly" | "monthly" | "yearly">(
    "weekly",
  );
  const [rruleInterval, setRruleInterval] = useState(1);
  const [rruleByDay, setRruleByDay] = useState<Record<string, boolean>>({
    MO: false, TU: false, WE: false, TH: false, FR: false, SA: false, SU: false,
  });
  const [rruleEnd, setRruleEnd] = useState<"never" | "count" | "date">("never");
  const [rruleCount, setRruleCount] = useState(10);
  const [rruleUntil, setRruleUntil] = useState("");

  const assigneeNeedsGoogle =
    assignee.kind === "member" &&
    getMember(assignee.id)?.google !== "connected";

  const toggleCar = (id: string) =>
    setSelectedCars((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleDay = (d: string) =>
    setRruleByDay((prev) => ({ ...prev, [d]: !prev[d] }));

  return (
    <>
      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="ev-title">Title</label>
        <input
          id="ev-title"
          className={styles.input}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Soccer practice"
          autoFocus
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ev-start">Start</label>
          <input
            id="ev-start"
            className={styles.input}
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ev-end">End</label>
          <input
            id="ev-end"
            className={styles.input}
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="ev-loc">Location</label>
        <input
          id="ev-loc"
          className={styles.input}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Riverside Park, Field 3"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="ev-desc">Description</label>
        <textarea
          id="ev-desc"
          className={styles.textarea}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Assign to a member</label>
        <AssigneePicker
          members={ACTIVE_MEMBERS}
          selected={assignee}
          onSelect={setAssignee}
        />
        {assigneeNeedsGoogle ? (
          <div
            style={{
              marginTop: 4,
              fontSize: 13,
              color: "var(--accent)",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
            role="note"
          >
            <AlertCircle size={14} strokeWidth={2} />
            {getMember((assignee as { kind: "member"; id: string }).id)?.name} doesn&apos;t have
            Google connected — this event won&apos;t sync to their calendar.
          </div>
        ) : null}
        {assignee.kind === "family-wide" ? (
          <div style={{ marginTop: 4, fontSize: 13, color: "var(--muted-fg)" }}>
            Unassigned events fan out to every active, Google-connected member.
          </div>
        ) : null}
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Cars</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {MOCK_CARS.map((c) => {
            const active = selectedCars.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggleCar(c.id)}
                aria-pressed={active}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 12px 6px 6px",
                  borderRadius: 999,
                  border: `2px solid ${active ? "var(--primary)" : "var(--border-color)"}`,
                  background: active ? "var(--muted)" : "var(--card)",
                  fontFamily: "inherit",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <CarAvatar color={c.color} size="sm" />
                {c.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className={styles.field}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
          style={{ alignSelf: "flex-start" }}
          onClick={() => setShowRecurrence((v) => !v)}
          aria-expanded={showRecurrence}
        >
          {showRecurrence ? "Hide recurrence" : "Add recurrence"}
        </button>
        {showRecurrence ? (
          <div
            style={{
              marginTop: 10,
              padding: 14,
              background: "var(--card)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius)",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {(["daily", "weekly", "monthly", "yearly"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setRruleFreq(f)}
                  aria-pressed={rruleFreq === f}
                  className={`${styles.btn} ${styles.btnSmall} ${
                    rruleFreq === f ? styles.btnPrimary : styles.btnGhost
                  }`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
              <span style={{ color: "var(--muted-fg)" }}>every</span>
              <input
                type="number"
                min={1}
                value={rruleInterval}
                onChange={(e) => setRruleInterval(Number(e.target.value))}
                className={styles.input}
                style={{ width: 80, padding: "8px 10px" }}
              />
              <span style={{ color: "var(--muted-fg)" }}>
                {rruleFreq === "daily"
                  ? "day(s)"
                  : rruleFreq === "weekly"
                  ? "week(s)"
                  : rruleFreq === "monthly"
                  ? "month(s)"
                  : "year(s)"}
              </span>
            </div>
            {rruleFreq === "weekly" ? (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {(["MO", "TU", "WE", "TH", "FR", "SA", "SU"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => toggleDay(d)}
                    aria-pressed={rruleByDay[d]}
                    className={`${styles.btn} ${styles.btnSmall} ${
                      rruleByDay[d] ? styles.btnPrimary : styles.btnGhost
                    }`}
                    style={{ minWidth: 44 }}
                  >
                    {d}
                  </button>
                ))}
              </div>
            ) : null}
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, flexWrap: "wrap" }}>
              <span style={{ color: "var(--muted-fg)" }}>ends</span>
              {(["never", "count", "date"] as const).map((e) => (
                <button
                  key={e}
                  type="button"
                  onClick={() => setRruleEnd(e)}
                  aria-pressed={rruleEnd === e}
                  className={`${styles.btn} ${styles.btnSmall} ${
                    rruleEnd === e ? styles.btnPrimary : styles.btnGhost
                  }`}
                >
                  {e === "never" ? "Never" : e === "count" ? "After N" : "On date"}
                </button>
              ))}
              {rruleEnd === "count" ? (
                <input
                  type="number"
                  min={1}
                  value={rruleCount}
                  onChange={(e) => setRruleCount(Number(e.target.value))}
                  className={styles.input}
                  style={{ width: 80, padding: "8px 10px" }}
                />
              ) : null}
              {rruleEnd === "date" ? (
                <input
                  type="date"
                  value={rruleUntil}
                  onChange={(e) => setRruleUntil(e.target.value)}
                  className={styles.input}
                  style={{ width: 160, padding: "8px 10px" }}
                />
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 10,
          marginTop: "auto",
          paddingTop: 12,
        }}
      >
        {!isNew ? (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnSmall} ${styles.btnDestructive}`}
            style={{ marginRight: "auto" }}
            onClick={onClose}
          >
            Delete
          </button>
        ) : null}
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
          onClick={onClose}
        >
          Cancel
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={onClose}
        >
          Save event
        </button>
      </div>
    </>
  );
}
