"use client";
import { ChevronLeft, ChevronRight, Filter, Plus } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
  eventsApi,
  type CarResponse,
  type EventResponse,
  type ExternalEventResponse,
  type MemberResponse,
} from "@/lib/api";
import { m } from "@/paraglide/messages.js";
import { formatDateTime } from "@/lib/intl";
import { getCurrentLocale } from "@/lib/i18n";

const HOUR_HEIGHT = 56;
const SLOT_MINUTES = 30;
const DEFAULT_SCROLL_HOUR = 7;

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
}

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

// Local-date key (YYYY-MM-DD in the user's timezone). Using toISOString()
// here would silently bucket events into the wrong day for any user not in
// UTC, since the server returns UTC ISO timestamps.
function localDateKey(d: Date): string {
  const yyyy = d.getFullYear();
  const mm = (d.getMonth() + 1).toString().padStart(2, "0");
  const dd = d.getDate().toString().padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function buildVisibleDays(anchor: Date, span: 1 | 3 | 7): DayInfo[] {
  const today = new Date();
  const weekdays = weekdayShortLabels();
  const start = startOfDay(anchor);
  if (span === 7) {
    const dayOfWeek = (start.getDay() + 6) % 7;
    start.setDate(start.getDate() - dayOfWeek);
  } else if (span === 3) {
    start.setDate(start.getDate() - 1);
  }
  return Array.from({ length: span }).map((_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const dowIndex = (d.getDay() + 6) % 7;
    return {
      iso: localDateKey(d),
      date: d,
      dow: weekdays[dowIndex],
      dom: d.getDate(),
      isToday: d.toDateString() === today.toDateString(),
    };
  });
}

function railColorForEvent(
  event: EventResponse,
  members: MemberResponse[],
): MemberColor | "family" {
  if (event.assignee_member_id == null && event.car_ids.length === 0) return "family";
  if (event.assignee_member_id) {
    const found = members.find((x) => x.id === event.assignee_member_id);
    return found?.color ?? "stone";
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

function formatHour(h: number): string {
  if (getCurrentLocale() === "pl") {
    return `${h.toString().padStart(2, "0")}:00`;
  }
  if (h === 0) return "12 AM";
  if (h === 12) return "12 PM";
  if (h < 12) return `${h} AM`;
  return `${h - 12} PM`;
}

function formatTimeShort(d: Date): string {
  const hh = d.getHours();
  const mm = d.getMinutes().toString().padStart(2, "0");
  if (getCurrentLocale() === "pl") {
    return `${hh.toString().padStart(2, "0")}:${mm}`;
  }
  const meridiem = hh >= 12 ? "PM" : "AM";
  const display = ((hh + 11) % 12) + 1;
  return `${display}:${mm} ${meridiem}`;
}

function minutesFromMidnight(d: Date): number {
  return d.getHours() * 60 + d.getMinutes();
}

function clampPositive(n: number): number {
  return n < 0 ? 0 : n;
}

export interface CalendarViewProps {
  members: MemberResponse[];
  cars: CarResponse[];
}

type Span = 1 | 3 | 7;

function defaultSpan(): Span {
  if (typeof window === "undefined") return 3;
  return window.innerWidth < 900 ? 3 : 7;
}

export function CalendarView({ members, cars }: CalendarViewProps) {
  const [anchor, setAnchor] = useState<Date>(() => new Date());
  const [span, setSpan] = useState<Span>(() => defaultSpan());
  const [events, setEvents] = useState<EventResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState<EventResponse | null>(null);
  const [editorDefaultStart, setEditorDefaultStart] = useState<Date | null>(null);

  const [filterOpen, setFilterOpen] = useState(false);
  const [filterOverrides, setFilterOverrides] = useState<Record<string, boolean>>({});
  const filters = useMemo(() => {
    const next: Record<string, boolean> = { cars: filterOverrides.cars ?? true };
    members.forEach((mem) => {
      next[mem.id] = filterOverrides[mem.id] ?? true;
    });
    return next;
  }, [members, filterOverrides]);
  const setFilters = useCallback(
    (updater: (prev: Record<string, boolean>) => Record<string, boolean>) => {
      setFilterOverrides((prev) => {
        const previousFull: Record<string, boolean> = { cars: prev.cars ?? true };
        members.forEach((mem) => {
          previousFull[mem.id] = prev[mem.id] ?? true;
        });
        return updater(previousFull);
      });
    },
    [members],
  );

  const days = useMemo(() => buildVisibleDays(anchor, span), [anchor, span]);
  const fromIso = useMemo(() => days[0].date.toISOString(), [days]);
  const toIso = useMemo(() => {
    const last = new Date(days[days.length - 1].date);
    last.setHours(23, 59, 59, 999);
    return last.toISOString();
  }, [days]);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await eventsApi.list({ from: fromIso, to: toIso });
      // Backend returns fridge[] + external[] separately (different shapes).
      // External events get projected to EventResponse-shaped rows so the
      // existing time-grid render path treats them uniformly. assignee_member_id
      // is set to the source member so they color-code by whose calendar they
      // came from.
      const externalAsEvents: EventResponse[] = res.external.map(
        (ext: ExternalEventResponse): EventResponse => ({
          id: ext.id,
          family_id: ext.family_id,
          title: ext.title || "(untitled)",
          description: ext.description,
          start_at: ext.start_at,
          end_at: ext.end_at,
          timezone: "",
          location: ext.location,
          assignee_member_id: ext.member_id,
          car_ids: [],
          rrule: ext.rrule,
          source: "external",
          source_member_id: ext.member_id,
          targets: [],
          linked_note_id: null,
          created_at: "",
          updated_at: "",
        }),
      );
      setEvents([...res.fridge, ...externalAsEvents]);
      setError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_load_events_failed();
      setError(msg);
    }
  }, [fromIso, toIso]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchEvents();
  }, [fetchEvents]);

  useFamilyEvents(fetchEvents);

  const filteredEvents = useMemo(() => {
    if (!events) return [];
    return events.filter((ev) => {
      if (ev.assignee_member_id) return filters[ev.assignee_member_id] ?? true;
      if (ev.car_ids.length > 0 && !ev.assignee_member_id) return filters.cars;
      return true;
    });
  }, [events, filters]);

  const eventsByIso = useMemo(() => {
    const map = new Map<string, EventResponse[]>();
    filteredEvents.forEach((ev) => {
      const iso = localDateKey(new Date(ev.start_at));
      if (!map.has(iso)) map.set(iso, []);
      map.get(iso)!.push(ev);
    });
    return map;
  }, [filteredEvents]);

  const openEditorForNew = (start?: Date) => {
    setEditingEvent(null);
    setEditorDefaultStart(start ?? null);
    setEditorOpen(true);
  };
  const openEditorForExisting = (ev: EventResponse) => {
    if (ev.source === "external") return;
    setEditingEvent(ev);
    setEditorDefaultStart(null);
    setEditorOpen(true);
  };

  const handleSaved = () => {
    void fetchEvents();
  };

  // Auto-scroll to ~7am on mount and when span changes.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = DEFAULT_SCROLL_HOUR * HOUR_HEIGHT;
  }, [span]);

  // Live "now" indicator — re-render every minute so the red line tracks.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const headerLabel = useMemo(() => {
    if (span === 1) {
      return formatDateTime(days[0].date, { weekday: "long", month: "short", day: "numeric" });
    }
    return `${formatDateTime(days[0].date, { month: "short", day: "numeric" })}–${formatDateTime(days[days.length - 1].date, { month: "short", day: "numeric" })}`;
  }, [days, span]);

  const stepDays = (delta: number) => {
    const d = new Date(anchor);
    d.setDate(d.getDate() + delta * span);
    setAnchor(d);
  };

  const HOURS = Array.from({ length: 24 }, (_, h) => h);

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-calendar"
      aria-labelledby="tab-calendar"
    >
      <TabHeader
        eyebrow={m.calendar_eyebrow_this_week({ range: headerLabel })}
        title={m.calendar_title()}
        right={
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <div className={styles.spanSwitch} role="group" aria-label={m.calendar_span_switch_aria()}>
              {([1, 3, 7] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`${styles.spanOption} ${span === s ? styles.spanOptionActive : ""}`}
                  onClick={() => setSpan(s)}
                  aria-pressed={span === s}
                >
                  {s === 1 ? m.calendar_days_one() : s === 3 ? m.calendar_days_three() : m.calendar_days_seven()}
                </button>
              ))}
            </div>
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
              onClick={() => stepDays(-1)}
            >
              <ChevronLeft size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              aria-label={m.calendar_next_week_aria()}
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
              onClick={() => stepDays(1)}
            >
              <ChevronRight size={18} strokeWidth={2.4} />
            </button>
            <div style={{ position: "relative" }}>
              <button
                type="button"
                aria-label={m.calendar_filter_button_aria()}
                aria-expanded={filterOpen}
                className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
                onClick={() => setFilterOpen((v) => !v)}
              >
                <Filter size={18} strokeWidth={2.4} />
              </button>
              {filterOpen ? (
                <FilterPopover
                  members={members}
                  cars={cars}
                  filters={filters}
                  setFilters={setFilters}
                  onClose={() => setFilterOpen(false)}
                />
              ) : null}
            </div>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimaryCompact}`}
              onClick={() => openEditorForNew()}
            >
              <Plus size={18} strokeWidth={2.4} />
              {m.calendar_new_event_button()}
            </button>
          </div>
        }
      />

      <div className={styles.calGridWrap}>
        {error ? <ErrorBanner message={error} onRetry={() => void fetchEvents()} /> : null}

        <div
          className={styles.calDayHeaderRow}
          style={{ gridTemplateColumns: `64px repeat(${days.length}, 1fr)` }}
        >
          <div className={styles.calGutterHeader} aria-hidden="true" />
          {days.map((d) => (
            <button
              key={d.iso}
              type="button"
              className={`${styles.calDayHeader} ${d.isToday ? styles.today : ""}`}
              aria-label={`${d.dow} ${d.dom}`}
              aria-current={d.isToday ? "date" : undefined}
              onClick={() => {
                setAnchor(d.date);
                if (span !== 1) setSpan(1);
              }}
            >
              <div className={styles.dow}>{d.dow}</div>
              <div className={styles.dom}>{d.dom}</div>
            </button>
          ))}
        </div>

        <div className={styles.calScroll} ref={scrollRef} aria-label={m.calendar_grid_aria()}>
          <div
            className={styles.calGrid}
            style={{
              gridTemplateColumns: `64px repeat(${days.length}, 1fr)`,
              height: HOUR_HEIGHT * 24,
            }}
          >
            <div className={styles.calGutter}>
              {HOURS.map((h) => (
                <div key={h} className={styles.calHourLabel} style={{ height: HOUR_HEIGHT }}>
                  {h === 0 ? "" : formatHour(h)}
                </div>
              ))}
            </div>

            {days.map((day) => (
              <DayColumn
                key={day.iso}
                day={day}
                events={eventsByIso.get(day.iso) ?? []}
                members={members}
                cars={cars}
                now={now}
                onSlotClick={(slotStart) => openEditorForNew(slotStart)}
                onEventClick={openEditorForExisting}
              />
            ))}
          </div>
        </div>
      </div>

      <EventEditorSheet
        open={editorOpen}
        event={editingEvent}
        members={members}
        cars={cars}
        defaultStart={editorDefaultStart}
        onClose={() => setEditorOpen(false)}
        onSaved={handleSaved}
      />
    </section>
  );
}

interface DayColumnProps {
  day: DayInfo;
  events: EventResponse[];
  members: MemberResponse[];
  cars: CarResponse[];
  now: Date;
  onSlotClick: (start: Date) => void;
  onEventClick: (ev: EventResponse) => void;
}

function DayColumn({ day, events, members, cars, now, onSlotClick, onEventClick }: DayColumnProps) {
  const slots = Array.from({ length: (24 * 60) / SLOT_MINUTES }, (_, i) => i);
  const isNowInThisDay = day.date.toDateString() === now.toDateString();
  const nowTop = (minutesFromMidnight(now) / 60) * HOUR_HEIGHT;

  return (
    <div className={`${styles.calCol} ${day.isToday ? styles.calColToday : ""}`}>
      {slots.map((slot) => {
        const minutes = slot * SLOT_MINUTES;
        const top = (minutes / 60) * HOUR_HEIGHT;
        const slotStart = new Date(day.date);
        slotStart.setHours(0, minutes, 0, 0);
        const isHourBoundary = minutes % 60 === 0;
        return (
          <button
            key={slot}
            type="button"
            className={`${styles.calSlot} ${isHourBoundary ? styles.calSlotHour : ""}`}
            style={{ top, height: (SLOT_MINUTES / 60) * HOUR_HEIGHT }}
            aria-label={m.calendar_grid_new_event_aria({ day: day.dow, time: formatTimeShort(slotStart) })}
            onClick={() => onSlotClick(slotStart)}
          />
        );
      })}

      {events.map((ev) => (
        <EventBlock
          key={ev.id}
          event={ev}
          members={members}
          cars={cars}
          dayStart={day.date}
          onClick={() => onEventClick(ev)}
        />
      ))}

      {isNowInThisDay ? (
        <div className={styles.calNowLine} style={{ top: nowTop }} aria-hidden="true">
          <span className={styles.calNowDot} />
        </div>
      ) : null}
    </div>
  );
}

interface EventBlockProps {
  event: EventResponse;
  members: MemberResponse[];
  cars: CarResponse[];
  dayStart: Date;
  onClick: () => void;
}

function EventBlock({ event, members, cars, dayStart, onClick }: EventBlockProps) {
  const start = new Date(event.start_at);
  const end = new Date(event.end_at);

  const dayMidnight = startOfDay(dayStart).getTime();
  const startMin = clampPositive((start.getTime() - dayMidnight) / 60_000);
  const rawEndMin = (end.getTime() - dayMidnight) / 60_000;
  const endMin = Math.min(rawEndMin, 24 * 60);
  const durMin = Math.max(20, endMin - startMin);

  const top = (startMin / 60) * HOUR_HEIGHT;
  const height = (durMin / 60) * HOUR_HEIGHT;

  const color = railColorForEvent(event, members);
  const cls = railClass(color);
  const isExternal = event.source === "external";
  const assignee = event.assignee_member_id
    ? members.find((mm) => mm.id === event.assignee_member_id)
    : null;

  return (
    <article
      className={`${styles.calEvent} ${cls} ${isExternal ? styles.calEventExternal : ""}`}
      style={{ top, height }}
      onClick={(e) => {
        e.stopPropagation();
        if (!isExternal) onClick();
      }}
      role={isExternal ? "article" : "button"}
      tabIndex={isExternal ? -1 : 0}
      onKeyDown={(e) => {
        if (isExternal) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      aria-label={`${event.title} — ${formatTimeShort(start)}`}
    >
      <div className={styles.calEventHeader}>
        <div className={styles.calEventTitle}>{event.title}</div>
        <div className={styles.calEventAvatars}>
          {assignee ? (
            <MemberAvatar
              initials={initialsFromName(assignee.name)}
              color={assignee.color}
              size="sm"
              title={assignee.name}
            />
          ) : null}
          {event.car_ids.map((cid) => {
            const c = cars.find((x) => x.id === cid);
            if (!c) return null;
            return <CarAvatar key={cid} color={c.color} size="sm" title={c.name} />;
          })}
        </div>
      </div>
      <div className={styles.calEventMeta}>
        <span>{formatTimeShort(start)}</span>
        {event.location ? <span>· {event.location}</span> : null}
      </div>
    </article>
  );
}

interface FilterPopoverProps {
  members: MemberResponse[];
  cars: CarResponse[];
  filters: Record<string, boolean>;
  setFilters: (updater: (prev: Record<string, boolean>) => Record<string, boolean>) => void;
  onClose: () => void;
}

function FilterPopover({ members, cars, filters, setFilters, onClose }: FilterPopoverProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div ref={ref} className={styles.filterPopover} role="dialog" aria-label={m.calendar_filter_popover_title()}>
      <div className={styles.sideTitle}>{m.calendar_filter_popover_title()}</div>
      <div className={styles.filterRow}>
        {members
          .filter((mem) => mem.status === "active")
          .map((mem) => (
            <label key={mem.id} className={styles.filterChip}>
              <MemberAvatar initials={initialsFromName(mem.name)} color={mem.color} />
              <span className={styles.name}>{mem.name}</span>
              <input
                type="checkbox"
                checked={filters[mem.id] ?? true}
                onChange={(e) => setFilters((f) => ({ ...f, [mem.id]: e.target.checked }))}
              />
            </label>
          ))}
        <label className={styles.filterChip}>
          <CarAvatar color="stone" />
          <span className={styles.name}>
            {m.calendar_filter_cars_label({ count: cars.filter((c) => c.status === "active").length })}
          </span>
          <input
            type="checkbox"
            checked={filters.cars ?? true}
            onChange={(e) => setFilters((f) => ({ ...f, cars: e.target.checked }))}
          />
        </label>
      </div>
    </div>
  );
}
