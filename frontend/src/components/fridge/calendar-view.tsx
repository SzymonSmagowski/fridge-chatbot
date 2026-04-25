"use client";
import { ChevronLeft, ChevronRight, Link2, MapPin, Plus, Repeat } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { CarAvatar } from "./car-avatar";
import { ErrorBanner } from "./error-banner";
import { EventEditorSheet } from "./event-editor-sheet";
import { MemberAvatar } from "./member-avatar";
import { TabHeader } from "./tab-header";
import { initialsFromName, type MemberColor } from "./types";
import { useFamilyEvents } from "@/lib/use-family-events";
import {
  ApiError,
  calendarSyncApi,
  eventsApi,
  type CarResponse,
  type EventResponse,
  type MemberResponse,
  type SyncStateResponse,
} from "@/lib/api";
import { m } from "@/paraglide/messages.js";
import { formatDateTime } from "@/lib/intl";
import { getCurrentLocale } from "@/lib/i18n";

function weekdayShortLabels(): string[] {
  return [
    m.weekday_short_mon(),
    m.weekday_short_tue(),
    m.weekday_short_wed(),
    m.weekday_short_thu(),
    m.weekday_short_fri(),
    m.weekday_short_sat(),
    m.weekday_short_sun(),
  ];
}

interface DayInfo {
  iso: string;
  date: Date;
  dow: string;
  dom: number;
  isToday: boolean;
  dots: MemberColor[];
}

function buildWeek(anchor: Date): DayInfo[] {
  const start = new Date(anchor);
  const dayOfWeek = (start.getDay() + 6) % 7; // Mon=0
  start.setDate(start.getDate() - dayOfWeek);
  start.setHours(0, 0, 0, 0);
  const today = new Date();
  const weekdays = weekdayShortLabels();
  return Array.from({ length: 7 }).map((_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return {
      iso: d.toISOString().slice(0, 10),
      date: d,
      dow: weekdays[i],
      dom: d.getDate(),
      isToday: d.toDateString() === today.toDateString(),
      dots: [],
    };
  });
}

function railColorForEvent(
  event: EventResponse,
  members: MemberResponse[],
): MemberColor | "family" {
  if (event.assignee_member_id == null && event.car_ids.length === 0) return "family";
  if (event.assignee_member_id) {
    const m = members.find((x) => x.id === event.assignee_member_id);
    return m?.color ?? "stone";
  }
  return "family";
}

function railClass(color: MemberColor | "family"): string {
  switch (color) {
    case "family":
      return styles.family;
    case "blue":
      return styles.blue;
    case "blush":
      return styles.blush;
    case "butter":
      return styles.butter;
    case "stone":
      return styles.stone;
    default:
      return "";
  }
}

function formatTime(d: Date): { time: string; meridiem: string } {
  // Polish uses 24h with no meridiem; English uses 12h + AM/PM.
  const hours = d.getHours();
  const minutes = d.getMinutes().toString().padStart(2, "0");
  if (getCurrentLocale() === "pl") {
    return { time: `${hours}:${minutes}`, meridiem: "" };
  }
  const displayHour = ((hours + 11) % 12) + 1;
  const meridiem = hours >= 12 ? "PM" : "AM";
  return { time: `${displayHour}:${minutes}`, meridiem };
}

function durationLabel(start: Date, end: Date): string {
  const ms = end.getTime() - start.getTime();
  const h = ms / 3_600_000;
  if (h >= 1) return `${h % 1 === 0 ? h : h.toFixed(1)}h`;
  return `${Math.round(ms / 60_000)}m`;
}

export interface CalendarViewProps {
  members: MemberResponse[];
  cars: CarResponse[];
}

export function CalendarView({ members, cars }: CalendarViewProps) {
  const [anchor, setAnchor] = useState<Date>(() => new Date());
  const [events, setEvents] = useState<EventResponse[] | null>(null);
  const [syncStates, setSyncStates] = useState<SyncStateResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState<EventResponse | null>(null);

  const [filterOverrides, setFilterOverrides] = useState<Record<string, boolean>>({});
  const filters = useMemo(() => {
    const next: Record<string, boolean> = { cars: filterOverrides.cars ?? true };
    members.forEach((m) => {
      next[m.id] = filterOverrides[m.id] ?? true;
    });
    return next;
  }, [members, filterOverrides]);
  const setFilters = useCallback(
    (updater: (prev: Record<string, boolean>) => Record<string, boolean>) => {
      setFilterOverrides((prev) => {
        const previousFull: Record<string, boolean> = { cars: prev.cars ?? true };
        members.forEach((m) => {
          previousFull[m.id] = prev[m.id] ?? true;
        });
        const next = updater(previousFull);
        return next;
      });
    },
    [members],
  );

  const week = useMemo(() => buildWeek(anchor), [anchor]);
  const fromIso = useMemo(() => week[0].date.toISOString(), [week]);
  const toIso = useMemo(() => {
    const last = new Date(week[6].date);
    last.setHours(23, 59, 59, 999);
    return last.toISOString();
  }, [week]);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await eventsApi.list({ from: fromIso, to: toIso });
      setEvents(res.items);
      setError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_load_events_failed();
      setError(msg);
    }
  }, [fromIso, toIso]);

  const fetchSync = useCallback(async () => {
    try {
      const states = await calendarSyncApi.state();
      setSyncStates(states);
    } catch {
      // sync state is best-effort; don't surface
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount + refetch when the visible week changes. setState happens
    // inside the awaited callback, not in the effect body — known false
    // positive of the React 19 `react-hooks/set-state-in-effect` rule.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchEvents();
    void fetchSync();
  }, [fetchEvents, fetchSync]);

  useFamilyEvents(fetchEvents);

  const filteredEvents = useMemo(() => {
    if (!events) return [];
    return events.filter((ev) => {
      if (ev.assignee_member_id) {
        return filters[ev.assignee_member_id] ?? true;
      }
      if (ev.car_ids.length > 0 && !ev.assignee_member_id) {
        return filters.cars;
      }
      return true; // family-wide
    });
  }, [events, filters]);

  // Populate week-strip dots
  const weekWithDots = useMemo(() => {
    const w = week.map((d) => ({ ...d, dots: [] as MemberColor[] }));
    filteredEvents.forEach((ev) => {
      const iso = new Date(ev.start_at).toISOString().slice(0, 10);
      const day = w.find((d) => d.iso === iso);
      if (!day) return;
      const color = railColorForEvent(ev, members);
      if (color === "family") day.dots.push("stone");
      else day.dots.push(color);
    });
    return w;
  }, [week, filteredEvents, members]);

  // Group events by day
  const grouped = useMemo(() => {
    const map = new Map<string, EventResponse[]>();
    filteredEvents
      .slice()
      .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())
      .forEach((ev) => {
        const iso = new Date(ev.start_at).toISOString().slice(0, 10);
        if (!map.has(iso)) map.set(iso, []);
        map.get(iso)!.push(ev);
      });
    return map;
  }, [filteredEvents]);

  const openEditorForNew = () => {
    setEditingEvent(null);
    setEditorOpen(true);
  };
  const openEditorForExisting = (ev: EventResponse) => {
    if (ev.source === "external") return; // read-only
    setEditingEvent(ev);
    setEditorOpen(true);
  };

  const handleSaved = () => {
    void fetchEvents();
  };

  const handlePullMember = async (memberId: string) => {
    try {
      await calendarSyncApi.pullMember(memberId);
      void fetchSync();
      void fetchEvents();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_sync_failed();
      toast.error(msg);
    }
  };

  const weekLabel = `${formatDateTime(week[0].date, { month: "short", day: "numeric" })}–${formatDateTime(week[6].date, { month: "short", day: "numeric" })}`;

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-calendar"
      aria-labelledby="tab-calendar"
    >
      <TabHeader
        eyebrow={m.calendar_eyebrow_this_week({ range: weekLabel })}
        title={m.calendar_title()}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
              onClick={() => setAnchor(new Date())}
            >
              {m.calendar_today_button()}
            </button>
            <button
              type="button"
              aria-label={m.calendar_prev_week_aria()}
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
              onClick={() => {
                const d = new Date(anchor);
                d.setDate(d.getDate() - 7);
                setAnchor(d);
              }}
            >
              <ChevronLeft size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              aria-label={m.calendar_next_week_aria()}
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
              onClick={() => {
                const d = new Date(anchor);
                d.setDate(d.getDate() + 7);
                setAnchor(d);
              }}
            >
              <ChevronRight size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimaryCompact}`}
              onClick={openEditorForNew}
            >
              <Plus size={18} strokeWidth={2.4} />
              {m.calendar_new_event_button()}
            </button>
          </div>
        }
      />

      <div className={styles.viewScroll}>
        {error ? <ErrorBanner message={error} onRetry={() => void fetchEvents()} /> : null}
        <div className={styles.calLayout}>
          <div className={styles.calMain}>
            <div className={styles.calWeekstrip}>
              {weekWithDots.map((d) => (
                <button
                  key={d.iso}
                  type="button"
                  className={`${styles.dayPill} ${d.isToday ? styles.today : ""}`}
                  aria-label={`${d.dow} ${d.dom}`}
                  aria-current={d.isToday ? "date" : undefined}
                  onClick={() => setAnchor(d.date)}
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
              {events === null ? (
                <div style={{ padding: 24, color: "var(--muted-fg)" }}>{m.calendar_loading_events()}</div>
              ) : grouped.size === 0 ? (
                <div
                  style={{
                    padding: 32,
                    textAlign: "center",
                    color: "var(--muted-fg)",
                    border: "2px dashed var(--border-color)",
                    borderRadius: "var(--radius-card)",
                  }}
                >
                  {m.calendar_empty_week()}
                </div>
              ) : (
                Array.from(grouped.entries()).map(([iso, items]) => {
                  const first = new Date(items[0].start_at);
                  const isToday = first.toDateString() === new Date().toDateString();
                  const dow = formatDateTime(first, { weekday: "short" }).toUpperCase();
                  const dom = first.getDate();
                  return (
                    <div key={iso} className={styles.agendaDay}>
                      <div className={`${styles.dayGutter} ${isToday ? styles.today : ""}`}>
                        <div className={styles.dow}>{dow}</div>
                        <div className={styles.dom}>{dom}</div>
                        {isToday ? <div className={styles.todayPill}>{m.calendar_today_pill()}</div> : null}
                      </div>
                      <div className={styles.agendaEvents}>
                        {items.map((ev) => (
                          <EventCard
                            key={ev.id}
                            event={ev}
                            members={members}
                            cars={cars}
                            onClick={() => openEditorForExisting(ev)}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <aside className={styles.calSide} aria-label="Calendar side panel">
            <div>
              <div className={styles.sideTitle}>Synced calendars</div>
              <div className={styles.sideSub}>Pulled per family settings.</div>
              <div className={styles.syncList}>
                {members
                  .filter((m) => m.status === "active")
                  .map((m) => {
                    const state = syncStates.find((s) => s.member_id === m.id);
                    const status = m.google.status;
                    const label =
                      status === "connected"
                        ? state?.last_pull_at
                          ? `${formatRelative(state.last_pull_at)} ago`
                          : "Syncing…"
                        : status === "not_connected"
                        ? "Not connected"
                        : status === "reconnect_needed"
                        ? "Reconnect"
                        : "Revoked";
                    const dotClass =
                      status === "connected"
                        ? styles.syncOk
                        : status === "reconnect_needed"
                        ? `${styles.syncOk} ${styles.syncWarn}`
                        : status === "not_connected"
                        ? `${styles.syncOk} ${styles.syncWarn}`
                        : `${styles.syncOk} ${styles.syncErr}`;
                    return (
                      <div key={m.id} className={styles.syncRow}>
                        <MemberAvatar
                          initials={initialsFromName(m.name)}
                          color={m.color}
                          size="md"
                        />
                        <div className={styles.name}>{m.name}</div>
                        <div className={styles.last}>{label}</div>
                        <button
                          type="button"
                          aria-label={`Sync ${m.name} now`}
                          onClick={() => void handlePullMember(m.id)}
                          style={{
                            background: "transparent",
                            border: "none",
                            cursor: "pointer",
                            padding: 0,
                          }}
                          disabled={status !== "connected"}
                        >
                          <span className={dotClass} title={`Sync status: ${status}`} />
                        </button>
                      </div>
                    );
                  })}
              </div>
            </div>

            <div>
              <div className={styles.sideTitle}>Show on board</div>
              <div className={styles.sideSub}>Toggle to filter the agenda.</div>
              <div className={styles.filterRow}>
                {members
                  .filter((m) => m.status === "active")
                  .map((m) => (
                    <label key={m.id} className={styles.filterChip}>
                      <MemberAvatar initials={initialsFromName(m.name)} color={m.color} />
                      <span className={styles.name}>{m.name}</span>
                      <input
                        type="checkbox"
                        checked={filters[m.id] ?? true}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, [m.id]: e.target.checked }))
                        }
                      />
                    </label>
                  ))}
                <label className={styles.filterChip}>
                  <CarAvatar color="stone" />
                  <span className={styles.name}>
                    Cars ({cars.filter((c) => c.status === "active").length})
                  </span>
                  <input
                    type="checkbox"
                    checked={filters.cars}
                    onChange={(e) => setFilters((f) => ({ ...f, cars: e.target.checked }))}
                  />
                </label>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <EventEditorSheet
        open={editorOpen}
        event={editingEvent}
        members={members}
        cars={cars}
        onClose={() => setEditorOpen(false)}
        onSaved={handleSaved}
      />
    </section>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.round(ms / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h`;
  const d = Math.round(hr / 24);
  return `${d}d`;
}

interface EventCardProps {
  event: EventResponse;
  members: MemberResponse[];
  cars: CarResponse[];
  onClick: () => void;
}

function EventCard({ event, members, cars, onClick }: EventCardProps) {
  const start = new Date(event.start_at);
  const end = new Date(event.end_at);
  const { time, meridiem } = formatTime(start);
  const dur = durationLabel(start, end);
  const color = railColorForEvent(event, members);
  const cls = railClass(color);

  const fanout = event.assignee_member_id == null && event.car_ids.length === 0 && event.targets.length > 0;

  return (
    <article
      className={`${styles.eventCard} ${cls}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className={styles.eventTime}>
        <div className={styles.t}>{time}</div>
        <div className={styles.meridiem}>
          {meridiem} · {dur}
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
          {event.rrule ? (
            <>
              {event.location ? <span className={styles.dividerDot} /> : null}
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Repeat size={12} strokeWidth={2} />
                Recurring
              </span>
            </>
          ) : null}
          {event.linked_note_id ? (
            <>
              <span className={styles.dividerDot} />
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Link2 size={12} strokeWidth={2} />
                Linked to fridge note
              </span>
            </>
          ) : null}
          {fanout ? (
            <>
              <span className={styles.dividerDot} />
              <span style={{ color: "var(--accent)", fontWeight: 700 }}>
                Synced to {event.targets.filter((t) => t.sync_status === "synced").length}{" "}
                calendars
              </span>
            </>
          ) : null}
          {event.source === "external" ? (
            <>
              <span className={styles.dividerDot} />
              <span style={{ color: "var(--muted-fg)" }}>External</span>
            </>
          ) : null}
        </div>
      </div>
      <div className={styles.eventAssignees}>
        {event.assignee_member_id
          ? (() => {
              const m = members.find((x) => x.id === event.assignee_member_id);
              if (!m) return null;
              return (
                <MemberAvatar
                  initials={initialsFromName(m.name)}
                  color={m.color}
                  size="md"
                  title={m.name}
                />
              );
            })()
          : null}
        {event.car_ids.map((cid) => {
          const c = cars.find((x) => x.id === cid);
          if (!c) return null;
          return <CarAvatar key={cid} color={c.color} size="md" title={c.name} />;
        })}
      </div>
    </article>
  );
}
