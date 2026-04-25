"use client";
import { ChevronLeft, ChevronRight, Link2, MapPin, Plus, Repeat, Sparkles } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { CarAvatar } from "./CarAvatar";
import { EventEditorSheet } from "./EventEditorSheet";
import { MemberAvatar } from "./MemberAvatar";
import { TabHeader } from "./TabHeader";
import {
  ACTIVE_MEMBERS,
  MOCK_CARS,
  MOCK_EVENTS,
  getCar,
  getMember,
} from "./mock-data";
import type { CalendarEvent, MemberColor } from "./types";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type DayInfo = {
  iso: string;
  dow: string;
  dom: number;
  isToday: boolean;
  dots: MemberColor[];
};

function buildWeek(today: Date): DayInfo[] {
  // Monday-anchored week containing today
  const start = new Date(today);
  const dayOfWeek = (start.getDay() + 6) % 7; // Mon=0
  start.setDate(start.getDate() - dayOfWeek);
  start.setHours(0, 0, 0, 0);

  return Array.from({ length: 7 }).map((_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    const isToday = d.toDateString() === today.toDateString();
    return { iso, dow: WEEKDAYS[i], dom: d.getDate(), isToday, dots: [] as MemberColor[] };
  });
}

export function CalendarView() {
  const today = new Date();
  const week = buildWeek(today);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    m_mom: true,
    m_dad: true,
    m_ola: true,
    cars: true,
  });

  // Populate week-strip dots from events
  MOCK_EVENTS.forEach((ev) => {
    const iso = ev.startAt.toISOString().slice(0, 10);
    const day = week.find((d) => d.iso === iso);
    if (!day) return;
    if (ev.railColor === "family") day.dots.push("stone");
    else day.dots.push(ev.railColor);
  });

  const filteredEvents = MOCK_EVENTS.filter((ev) => {
    const memberIds = ev.assignees
      .filter((a) => a.kind === "member")
      .map((a) => (a.kind === "member" ? a.id : ""));
    const hasCars = ev.assignees.some((a) => a.kind === "car");

    if (ev.fanout) return true;
    if (hasCars && !filters.cars && memberIds.length === 0) return false;
    if (memberIds.length > 0) {
      const anyVisible = memberIds.some(
        (id) => filters[id as keyof typeof filters],
      );
      return anyVisible;
    }
    return true;
  });

  // Group events by day
  const grouped = new Map<string, CalendarEvent[]>();
  filteredEvents
    .slice()
    .sort((a, b) => a.startAt.getTime() - b.startAt.getTime())
    .forEach((ev) => {
      const iso = ev.startAt.toISOString().slice(0, 10);
      if (!grouped.has(iso)) grouped.set(iso, []);
      grouped.get(iso)!.push(ev);
    });

  const openEditorForNew = () => {
    setEditingEventId(null);
    setEditorOpen(true);
  };
  const openEditorForExisting = (id: string) => {
    setEditingEventId(id);
    setEditorOpen(true);
  };

  const editingEvent = editingEventId
    ? MOCK_EVENTS.find((e) => e.id === editingEventId) ?? null
    : null;

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-calendar"
      aria-labelledby="tab-calendar"
    >
      <TabHeader
        eyebrow="This Week · April 20–26"
        title="Calendar"
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}>
              Today
            </button>
            <button
              type="button"
              aria-label="Previous week"
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
            >
              <ChevronLeft size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              aria-label="Next week"
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
            >
              <ChevronRight size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimaryCompact}`}
              onClick={openEditorForNew}
            >
              <Plus size={18} strokeWidth={2.4} />
              New event
            </button>
          </div>
        }
      />

      <div className={styles.viewScroll}>
        <div className={styles.calLayout}>
          <div className={styles.calMain}>
            <div className={styles.calWeekstrip}>
              {week.map((d) => (
                <button
                  key={d.iso}
                  type="button"
                  className={`${styles.dayPill} ${d.isToday ? styles.today : ""}`}
                  aria-label={`${d.dow} ${d.dom}`}
                  aria-current={d.isToday ? "date" : undefined}
                >
                  <div className={styles.dow}>{d.dow}</div>
                  <div className={styles.dom}>{d.dom}</div>
                  <div className={styles.dotrow}>
                    {d.dots.slice(0, 3).map((c, i) => (
                      <span
                        key={i}
                        className={styles.tinydot}
                        style={{ background: d.isToday ? "#fff" : `var(--member-${c})` }}
                      />
                    ))}
                  </div>
                </button>
              ))}
            </div>

            <div className={styles.agenda}>
              {Array.from(grouped.entries()).map(([iso, events]) => {
                const isToday =
                  new Date(iso).toDateString() === today.toDateString();
                const first = events[0];
                const dow = first.startAt
                  .toLocaleDateString(undefined, { weekday: "short" })
                  .toUpperCase();
                const dom = first.startAt.getDate();
                return (
                  <div key={iso} className={styles.agendaDay}>
                    <div className={`${styles.dayGutter} ${isToday ? styles.today : ""}`}>
                      <div className={styles.dow}>{dow}</div>
                      <div className={styles.dom}>{dom}</div>
                      {isToday ? <div className={styles.todayPill}>TODAY</div> : null}
                    </div>
                    <div className={styles.agendaEvents}>
                      {events.map((ev) => (
                        <EventCard key={ev.id} event={ev} onClick={openEditorForExisting} />
                      ))}
                    </div>
                  </div>
                );
              })}
              {grouped.size === 0 ? (
                <div
                  style={{
                    padding: 32,
                    textAlign: "center",
                    color: "var(--muted-fg)",
                    border: "2px dashed var(--border-color)",
                    borderRadius: "var(--radius-card)",
                  }}
                >
                  No events this week. Tap <b>New event</b> to add one, or connect a member&apos;s
                  Google account in Settings.
                </div>
              ) : null}
            </div>
          </div>

          <aside className={styles.calSide} aria-label="Calendar side panel">
            <div>
              <div className={styles.sideTitle}>Synced calendars</div>
              <div className={styles.sideSub}>Pulled every 5 min via Google Calendar API.</div>
              <div className={styles.syncList}>
                {ACTIVE_MEMBERS.map((m) => (
                  <div key={m.id} className={styles.syncRow}>
                    <MemberAvatar initials={m.initials} color={m.color} size="md" />
                    <div className={styles.name}>{m.name}</div>
                    <div className={styles.last}>
                      {m.google === "connected"
                        ? "2m ago"
                        : m.google === "pending"
                        ? "Not connected"
                        : m.google === "reconnect-needed"
                        ? "Reconnect"
                        : "—"}
                    </div>
                    <span
                      className={`${styles.syncOk} ${
                        m.google === "reconnect-needed"
                          ? styles.syncWarn
                          : m.google === "pending"
                          ? styles.syncWarn
                          : ""
                      }`}
                      title={`Sync status: ${m.google}`}
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className={styles.sideTitle}>Show on board</div>
              <div className={styles.sideSub}>Toggle to filter the agenda.</div>
              <div className={styles.filterRow}>
                {ACTIVE_MEMBERS.map((m) => (
                  <label key={m.id} className={styles.filterChip}>
                    <MemberAvatar initials={m.initials} color={m.color} />
                    <span className={styles.name}>{m.name}</span>
                    <input
                      type="checkbox"
                      checked={filters[m.id as keyof typeof filters] ?? true}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, [m.id]: e.target.checked }))
                      }
                    />
                  </label>
                ))}
                <label className={styles.filterChip}>
                  <CarAvatar color="stone" />
                  <span className={styles.name}>Cars ({MOCK_CARS.length})</span>
                  <input
                    type="checkbox"
                    checked={filters.cars}
                    onChange={(e) => setFilters((f) => ({ ...f, cars: e.target.checked }))}
                  />
                </label>
              </div>
            </div>

            <div>
              <div className={styles.sideTitle}>AI suggestions</div>
              <div className={styles.sideSub}>From this week&apos;s chat &amp; notes.</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div className={`${styles.suggestionCard} ${styles.fromChat}`}>
                  <div className={styles.lab}>
                    <Sparkles size={11} strokeWidth={2.4} style={{ marginRight: 4, verticalAlign: -1 }} />
                    From chat earlier
                  </div>
                  &quot;Remind Ola about permission slip Friday&quot; — <b>Add as event?</b>
                </div>
                <div className={styles.suggestionCard}>
                  <div className={styles.lab}>
                    <Sparkles size={11} strokeWidth={2.4} style={{ marginRight: 4, verticalAlign: -1 }} />
                    Pattern detected
                  </div>
                  Soccer practice is on every Mon/Wed. <b>Make it recurring?</b>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <EventEditorSheet
        open={editorOpen}
        event={editingEvent}
        onClose={() => setEditorOpen(false)}
      />
    </section>
  );
}

function EventCard({
  event,
  onClick,
}: {
  event: CalendarEvent;
  onClick: (id: string) => void;
}) {
  const railClass =
    event.railColor === "family"
      ? styles.family
      : event.railColor === "blue"
      ? styles.blue
      : event.railColor === "blush"
      ? styles.blush
      : event.railColor === "butter"
      ? styles.butter
      : event.railColor === "stone"
      ? styles.stone
      : "";

  const hours = event.startAt.getHours();
  const displayHour = ((hours + 11) % 12) + 1;
  const minutes = event.startAt.getMinutes().toString().padStart(2, "0");
  const meridiem = hours >= 12 ? "PM" : "AM";
  const durationMs = event.endAt.getTime() - event.startAt.getTime();
  const durationHours = durationMs / 3_600_000;
  const durationLabel =
    durationHours >= 1 ? `${durationHours}h` : `${Math.round(durationMs / 60_000)}m`;

  return (
    <article
      className={`${styles.eventCard} ${railClass}`}
      onClick={() => onClick(event.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(event.id);
        }
      }}
    >
      <div className={styles.eventTime}>
        <div className={styles.t}>{`${displayHour}:${minutes}`}</div>
        <div className={styles.meridiem}>
          {meridiem} · {durationLabel}
        </div>
      </div>
      <div className={styles.eventBody}>
        <div className={styles.eventTitle}>{event.title}</div>
        <div className={styles.eventMeta}>
          {event.location ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <MapPin size={12} strokeWidth={2} />
              {event.location}
            </span>
          ) : null}
          {event.rruleLabel ? (
            <>
              {event.location ? <span className={styles.dividerDot} /> : null}
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Repeat size={12} strokeWidth={2} />
                {event.rruleLabel}
              </span>
            </>
          ) : null}
          {event.linkedNoteId ? (
            <>
              <span className={styles.dividerDot} />
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Link2 size={12} strokeWidth={2} />
                Linked to fridge note
              </span>
            </>
          ) : null}
          {event.fanout && event.fanoutLabel ? (
            <>
              <span className={styles.dividerDot} />
              <span style={{ color: "var(--accent)", fontWeight: 700 }}>
                {event.fanoutLabel}
              </span>
            </>
          ) : null}
        </div>
      </div>
      <div className={styles.eventAssignees}>
        {event.assignees.map((a, i) => {
          if (a.kind === "member") {
            const m = getMember(a.id);
            if (!m) return null;
            return (
              <MemberAvatar
                key={`${a.id}-${i}`}
                initials={m.initials}
                color={m.color}
                size="md"
                title={m.name}
              />
            );
          }
          if (a.kind === "car") {
            const c = getCar(a.id);
            if (!c) return null;
            return <CarAvatar key={`${a.id}-${i}`} color={c.color} size="md" title={c.name} />;
          }
          return null;
        })}
      </div>
    </article>
  );
}
