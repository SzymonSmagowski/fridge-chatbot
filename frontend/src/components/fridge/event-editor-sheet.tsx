"use client";
import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { AssigneePicker, type AssigneeSelection } from "./assignee-picker";
import { CarAvatar } from "./car-avatar";
import { ConfirmDialog } from "./confirm-dialog";
import { FridgeSheet } from "./sheet";
import {
  ApiError,
  eventsApi,
  type CarResponse,
  type EventResponse,
  type EventScope,
  type MemberResponse,
} from "@/lib/api";

export interface EventEditorSheetProps {
  open: boolean;
  event: EventResponse | null;
  members: MemberResponse[];
  cars: CarResponse[];
  onClose: () => void;
  onSaved: () => void;
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

function fromLocalInputValue(s: string): string {
  // datetime-local has no timezone; parse as local.
  const d = new Date(s);
  return d.toISOString();
}

type Frequency = "daily" | "weekly" | "monthly" | "yearly";
type RecurrenceEnd = "never" | "count" | "date";

function buildRrule(
  freq: Frequency,
  interval: number,
  byDay: Record<string, boolean>,
  end: RecurrenceEnd,
  count: number,
  until: string,
): string {
  const parts: string[] = [`FREQ=${freq.toUpperCase()}`];
  if (interval > 1) parts.push(`INTERVAL=${interval}`);
  if (freq === "weekly") {
    const days = Object.entries(byDay)
      .filter(([, on]) => on)
      .map(([d]) => d);
    if (days.length > 0) parts.push(`BYDAY=${days.join(",")}`);
  }
  if (end === "count") parts.push(`COUNT=${count}`);
  if (end === "date" && until)
    parts.push(`UNTIL=${until.replace(/-/g, "")}T000000Z`);
  return parts.join(";");
}

export function EventEditorSheet({
  open,
  event,
  members,
  cars,
  onClose,
  onSaved,
}: EventEditorSheetProps) {
  const key = event?.id ?? (open ? "new" : "closed");
  return (
    <FridgeSheet
      open={open}
      onClose={onClose}
      title={event ? "Edit event" : "New event"}
    >
      <EventForm
        key={key}
        event={event}
        members={members}
        cars={cars}
        onClose={onClose}
        onSaved={onSaved}
      />
    </FridgeSheet>
  );
}

function EventForm({
  event,
  members,
  cars,
  onClose,
  onSaved,
}: {
  event: EventResponse | null;
  members: MemberResponse[];
  cars: CarResponse[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = !event;
  const initialStart = event ? new Date(event.start_at) : new Date();
  const initialEnd = event
    ? new Date(event.end_at)
    : new Date(initialStart.getTime() + 60 * 60 * 1000);
  const initialAssignee: AssigneeSelection = event?.assignee_member_id
    ? { kind: "member", id: event.assignee_member_id }
    : { kind: "family-wide" };
  const initialCars = event?.car_ids ?? [];

  const [title, setTitle] = useState(event?.title ?? "");
  const [start, setStart] = useState(toLocalInputValue(initialStart));
  const [end, setEnd] = useState(toLocalInputValue(initialEnd));
  const [location, setLocation] = useState(event?.location ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [assignee, setAssignee] = useState<AssigneeSelection>(initialAssignee);
  const [selectedCars, setSelectedCars] = useState<string[]>(initialCars);
  const [showRecurrence, setShowRecurrence] = useState(Boolean(event?.rrule));
  const [rruleFreq, setRruleFreq] = useState<Frequency>("weekly");
  const [rruleInterval, setRruleInterval] = useState(1);
  const [rruleByDay, setRruleByDay] = useState<Record<string, boolean>>({
    MO: false, TU: false, WE: false, TH: false, FR: false, SA: false, SU: false,
  });
  const [rruleEnd, setRruleEnd] = useState<RecurrenceEnd>("never");
  const [rruleCount, setRruleCount] = useState(10);
  const [rruleUntil, setRruleUntil] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [scopeAsk, setScopeAsk] = useState<null | "save" | "delete">(null);

  const assigneeNeedsGoogle =
    assignee.kind === "member" &&
    members.find((m) => m.id === assignee.id)?.google.status !== "connected";

  const toggleCar = (id: string) =>
    setSelectedCars((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  const toggleDay = (d: string) =>
    setRruleByDay((prev) => ({ ...prev, [d]: !prev[d] }));

  const buildBody = () => ({
    title: title.trim(),
    description: description.trim() || null,
    start_at: fromLocalInputValue(start),
    end_at: fromLocalInputValue(end),
    location: location.trim() || null,
    assignee_member_id: assignee.kind === "member" ? assignee.id : null,
    car_ids: selectedCars,
    rrule: showRecurrence
      ? buildRrule(rruleFreq, rruleInterval, rruleByDay, rruleEnd, rruleCount, rruleUntil)
      : null,
  });

  const persistSave = async (scope: EventScope = "instance") => {
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      const body = buildBody();
      if (event) {
        await eventsApi.update(event.id, body, scope);
      } else {
        await eventsApi.create(body);
      }
      onSaved();
      onClose();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to save event";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const persistDelete = async (scope: EventScope = "instance") => {
    if (!event) return;
    setSubmitting(true);
    try {
      await eventsApi.delete(event.id, scope);
      onSaved();
      onClose();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to delete event";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSave = () => {
    if (event && event.rrule) {
      setScopeAsk("save");
      return;
    }
    void persistSave("instance");
  };

  const handleDelete = () => {
    if (event && event.rrule) {
      setScopeAsk("delete");
      return;
    }
    void persistDelete("instance");
  };

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
          members={members}
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
            {members.find((m) => assignee.kind === "member" && m.id === assignee.id)?.name}{" "}
            doesn&apos;t have Google connected — this event won&apos;t sync to their calendar.
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
          {cars
            .filter((c) => c.status === "active")
            .map((c) => {
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
              borderRadius: "var(--fridge-radius)",
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
              {(["never", "count", "date"] as const).map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setRruleEnd(opt)}
                  aria-pressed={rruleEnd === opt}
                  className={`${styles.btn} ${styles.btnSmall} ${
                    rruleEnd === opt ? styles.btnPrimary : styles.btnGhost
                  }`}
                >
                  {opt === "never" ? "Never" : opt === "count" ? "After N" : "On date"}
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
            onClick={handleDelete}
            disabled={submitting}
          >
            Delete
          </button>
        ) : null}
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
          onClick={onClose}
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={handleSave}
          disabled={submitting || !title.trim()}
        >
          Save event
        </button>
      </div>

      <ConfirmDialog
        open={scopeAsk !== null}
        title="Apply to…"
        body="This is a recurring event. Choose whether to change just this occurrence or this and all future occurrences."
        confirmLabel="This event only"
        cancelLabel="This and all future"
        destructive={scopeAsk === "delete"}
        onConfirm={() => {
          const op = scopeAsk;
          setScopeAsk(null);
          if (op === "delete") void persistDelete("instance");
          else void persistSave("instance");
        }}
        onCancel={() => {
          const op = scopeAsk;
          setScopeAsk(null);
          if (op === "delete") void persistDelete("all_future");
          else if (op === "save") void persistSave("all_future");
        }}
      />
    </>
  );
}
