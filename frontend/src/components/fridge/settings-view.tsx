"use client";
import { Check, Clock, LogIn, MessageSquare, MoreHorizontal, Pencil, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { AddCarSheet } from "./add-car-sheet";
import { AddMemberSheet } from "./add-member-sheet";
import { CarAvatar } from "./car-avatar";
import { ConfirmDialog } from "./confirm-dialog";
import { ConnectGoogleModal } from "./connect-google-modal";
import { ErrorBanner } from "./error-banner";
import { FeedbackModal } from "./feedback-modal";
import { LanguageSwitcher } from "./language-switcher";
import { MemberAvatar } from "./member-avatar";
import { TabHeader } from "./tab-header";
import { m } from "@/paraglide/messages.js";
import { initialsFromName } from "./types";
import {
  ApiError,
  calendarSyncApi,
  carsApi,
  familyApi,
  membersApi,
  type CarResponse,
  type FamilyPreferencesResponse,
  type FamilyResponse,
  type MemberResponse,
  type SyncStateResponse,
} from "@/lib/api";

export interface SettingsViewProps {
  family: FamilyResponse | null;
  members: MemberResponse[];
  cars: CarResponse[];
  /** Re-fetch family + members + cars from parent. */
  refresh: () => Promise<void> | void;
}

export function SettingsView({ family, members, cars, refresh }: SettingsViewProps) {
  const [extraMembers, setExtraMembers] = useState<MemberResponse[]>([]);
  const [extraCars, setExtraCars] = useState<CarResponse[]>([]);
  const allMembers = useMemo(() => {
    if (extraMembers.length === 0) return members;
    const ids = new Set(members.map((m) => m.id));
    return [...members, ...extraMembers.filter((m) => !ids.has(m.id))];
  }, [members, extraMembers]);
  const allCars = useMemo(() => {
    if (extraCars.length === 0) return cars;
    const ids = new Set(cars.map((c) => c.id));
    return [...cars, ...extraCars.filter((c) => !ids.has(c.id))];
  }, [cars, extraCars]);

  const [prefs, setPrefs] = useState<FamilyPreferencesResponse | null>(null);
  const [prefsError, setPrefsError] = useState<string | null>(null);

  const [syncStates, setSyncStates] = useState<SyncStateResponse[]>([]);

  const [memberSheet, setMemberSheet] = useState<
    { mode: "create" } | { mode: "edit"; member: MemberResponse } | null
  >(null);
  const [carSheet, setCarSheet] = useState<
    { mode: "create" } | { mode: "edit"; car: CarResponse } | null
  >(null);

  const [confirm, setConfirm] = useState<null | {
    title: string;
    body: string;
    confirmLabel: string;
    destructive?: boolean;
    onConfirm: () => void;
  }>(null);

  const [connectTarget, setConnectTarget] = useState<{
    memberId: string;
    memberName: string;
  } | null>(null);

  const [feedbackOpen, setFeedbackOpen] = useState(false);

  const fetchPrefs = useCallback(async () => {
    try {
      const p = await familyApi.getPreferences();
      setPrefs(p);
      setPrefsError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load preferences";
      setPrefsError(msg);
    }
  }, []);

  const fetchSync = useCallback(async () => {
    try {
      const states = await calendarSyncApi.state();
      setSyncStates(states);
    } catch {
      // best-effort — don't surface
    }
  }, []);

  const handlePullMember = useCallback(async (memberId: string) => {
    try {
      await calendarSyncApi.pullMember(memberId);
      void fetchSync();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_sync_failed();
      toast.error(msg);
    }
  }, [fetchSync]);

  useEffect(() => {
    // setState happens inside the awaited callback, not in the effect body —
    // known false positive of the React 19 `react-hooks/set-state-in-effect` rule.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchPrefs();
    void fetchSync();
  }, [fetchPrefs, fetchSync]);

  const refetchMembers = useCallback(async () => {
    try {
      const list = await membersApi.list("all");
      // Parent owns the active set; we hold the inactive overflow.
      setExtraMembers(list.filter((m) => m.status === "inactive"));
      await refresh();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load members";
      toast.error(msg);
    }
  }, [refresh]);

  const refetchCars = useCallback(async () => {
    try {
      const list = await carsApi.list("all");
      setExtraCars(list.filter((c) => c.status === "inactive"));
      await refresh();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load cars";
      toast.error(msg);
    }
  }, [refresh]);

  const activeMembers = allMembers.filter((m) => m.status === "active");
  const activeCars = allCars.filter((c) => c.status === "active");

  const setMemberInactive = (m: MemberResponse) => {
    setConfirm({
      title: `Set ${m.name} inactive?`,
      body: `${m.name} will be hidden from assignee pickers. Existing notes and events still show their name and color. You can reactivate at any time.`,
      confirmLabel: "Set inactive",
      destructive: true,
      onConfirm: async () => {
        try {
          await membersApi.setInactive(m.id);
          setConfirm(null);
          void refetchMembers();
        } catch (err) {
          const msg = err instanceof ApiError ? err.message : "Failed to set inactive";
          toast.error(msg);
        }
      },
    });
  };

  const setCarInactive = (c: CarResponse) => {
    setConfirm({
      title: `Set ${c.name} inactive?`,
      body: `${c.name} will be hidden from assignee pickers. Existing notes and events still show its name. You can reactivate at any time.`,
      confirmLabel: "Set inactive",
      destructive: true,
      onConfirm: async () => {
        try {
          await carsApi.setInactive(c.id);
          setConfirm(null);
          void refetchCars();
        } catch (err) {
          const msg = err instanceof ApiError ? err.message : "Failed to set inactive";
          toast.error(msg);
        }
      },
    });
  };

  const deleteCarPermanently = (c: CarResponse) => {
    setConfirm({
      title: `Delete ${c.name}?`,
      body: `This is permanent. Past notes and events will keep showing "${c.name}" as plain text but will no longer link to a car record.`,
      confirmLabel: "Delete permanently",
      destructive: true,
      onConfirm: async () => {
        try {
          await carsApi.delete(c.id);
          setConfirm(null);
          void refetchCars();
        } catch (err) {
          const msg = err instanceof ApiError ? err.message : "Failed to delete car";
          toast.error(msg);
        }
      },
    });
  };

  const updatePrefs = async (patch: Partial<FamilyPreferencesResponse>) => {
    if (!prefs) return;
    const next = { ...prefs, ...patch };
    setPrefs(next);
    try {
      const updated = await familyApi.patchPreferences(patch);
      setPrefs(updated);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to save preference";
      toast.error(msg);
      setPrefs(prefs); // revert
    }
  };

  const connectGoogle = useCallback((member: MemberResponse) => {
    setConnectTarget({ memberId: member.id, memberName: member.name });
  }, []);

  const onConnectComplete = useCallback(() => {
    setConnectTarget(null);
    void refetchMembers();
  }, [refetchMembers]);

  const familyName = family?.name ?? "Your Family";
  const familyInitial = familyName.charAt(0);
  const familyCreated = family
    ? new Date(family.created_at).toLocaleDateString(undefined, {
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : "—";

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-settings"
      aria-labelledby="tab-settings"
    >
      <TabHeader eyebrow="Device & Family" title="Settings" />

      <div className={styles.viewScroll}>
        <div className={styles.settingsLayout}>
          <div className={styles.familyBanner}>
            <div className={styles.crest}>{familyInitial}</div>
            <div className={styles.info}>
              <h3>{familyName}</h3>
              <p>
                Paired to this fridge · {activeMembers.length} members · {activeCars.length} cars ·
                created {familyCreated}
              </p>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                gap: 6,
              }}
            >
              <div className={styles.pairedTag}>
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: "var(--success)",
                  }}
                  aria-hidden="true"
                />
                Paired
              </div>
            </div>
          </div>

          <div className={styles.settingsCard}>
            <h3>
              Members
              <span className={`${styles.pill} ${styles.pillNeutral}`}>
                {activeMembers.length} active
              </span>
            </h3>
            <div className={styles.sub}>
              People who are assigned to notes and whose calendars sync to the fridge.
            </div>

            <div className={styles.memberList}>
              {activeMembers.map((m) => (
                <MemberRow
                  key={m.id}
                  member={m}
                  onEdit={() => setMemberSheet({ mode: "edit", member: m })}
                  onSetInactive={() => setMemberInactive(m)}
                  onConnectGoogle={() => connectGoogle(m)}
                />
              ))}
            </div>

            <button
              type="button"
              className={styles.addRow}
              onClick={() => setMemberSheet({ mode: "create" })}
            >
              <Plus size={18} strokeWidth={2.4} />
              Add a family member
            </button>
          </div>

          <SyncedCalendarsCard
            members={activeMembers}
            syncStates={syncStates}
            onPull={handlePullMember}
          />

          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className={styles.settingsCard}>
              <h3>
                {m.settings_cars_card_title()}
                <span className={`${styles.pill} ${styles.pillNeutral}`}>
                  {m.settings_active_count_pill({ count: activeCars.length })}
                </span>
              </h3>
              <div className={styles.sub}>{m.settings_cars_subtitle()}</div>

              <div className={styles.memberList}>
                {activeCars.map((c) => (
                  <CarRow
                    key={c.id}
                    car={c}
                    onEdit={() => setCarSheet({ mode: "edit", car: c })}
                    onSetInactive={() => setCarInactive(c)}
                    onDelete={() => deleteCarPermanently(c)}
                  />
                ))}
              </div>

              <button
                type="button"
                className={styles.addRow}
                onClick={() => setCarSheet({ mode: "create" })}
              >
                <Plus size={18} strokeWidth={2.4} />
                {m.settings_add_car_button()}
              </button>
            </div>

            <div className={styles.settingsCard}>
              <h3>{m.settings_prefs_card_title()}</h3>
              <div className={styles.sub}>{m.settings_prefs_subtitle()}</div>

              {prefsError ? (
                <ErrorBanner message={prefsError} onRetry={() => void fetchPrefs()} />
              ) : prefs ? (
                <PreferencesPanel prefs={prefs} onChange={updatePrefs} />
              ) : (
                <div style={{ color: "var(--muted-fg)" }}>{m.settings_loading_prefs()}</div>
              )}
            </div>

            {/* TODO(future): once multi-device pairing lands, persist to
                family_preferences.language so the kiosk picks it up server-side. */}
            <div className={styles.settingsCard}>
              <h3>{m.language_label()}</h3>
              <div className={styles.sub}>{m.language_subtitle()}</div>
              <div style={{ marginTop: 14 }}>
                <LanguageSwitcher />
              </div>
            </div>

            <div className={styles.settingsCard}>
              <h3>{m.feedback_modal_title()}</h3>
              <div className={styles.sub}>{m.feedback_modal_description()}</div>
              <div style={{ marginTop: 14 }}>
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnPrimary} ${styles.btnSmall}`}
                  onClick={() => setFeedbackOpen(true)}
                >
                  <MessageSquare size={16} strokeWidth={2.2} />
                  {m.feedback_button_label()}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <AddMemberSheet
        state={memberSheet}
        onClose={() => setMemberSheet(null)}
        onSaved={() => {
          setMemberSheet(null);
          void refetchMembers();
        }}
      />

      <AddCarSheet
        state={carSheet}
        onClose={() => setCarSheet(null)}
        onSaved={() => {
          setCarSheet(null);
          void refetchCars();
        }}
      />

      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title ?? ""}
        body={confirm?.body ?? ""}
        confirmLabel={confirm?.confirmLabel ?? "Confirm"}
        destructive={confirm?.destructive}
        onConfirm={() => confirm?.onConfirm()}
        onCancel={() => setConfirm(null)}
      />

      <ConnectGoogleModal
        open={connectTarget !== null}
        memberId={connectTarget?.memberId ?? null}
        memberName={connectTarget?.memberName ?? null}
        onClose={onConnectComplete}
      />

      <FeedbackModal
        open={feedbackOpen}
        threadId={null}
        onClose={() => setFeedbackOpen(false)}
      />
    </section>
  );
}

function MemberRow({
  member,
  onEdit,
  onSetInactive,
  onConnectGoogle,
}: {
  member: MemberResponse;
  onEdit: () => void;
  onSetInactive: () => void;
  onConnectGoogle: () => void;
}) {
  const status = member.google.status;
  return (
    <div className={styles.memberRow}>
      <MemberAvatar
        initials={initialsFromName(member.name)}
        color={member.color}
        size="lg"
      />
      <div className={styles.memberInfo}>
        <div className={styles.memberName}>
          {member.name}
          {member.nickname ? (
            <span style={{ color: "var(--muted-fg)", fontWeight: 500, fontSize: 13, marginLeft: 6 }}>
              ({member.nickname})
            </span>
          ) : null}
        </div>
        <div className={styles.memberMeta}>
          {member.google.email ? <span>{member.google.email}</span> : null}
          {status === "connected" ? (
            <span className={`${styles.pill} ${styles.pillConnected}`}>
              <Check size={10} strokeWidth={3} />
              Google synced
            </span>
          ) : status === "not_connected" ? (
            <span className={`${styles.pill} ${styles.pillPending}`}>
              <Clock size={10} strokeWidth={2.4} />
              No Google account yet
            </span>
          ) : status === "reconnect_needed" ? (
            <span className={`${styles.pill} ${styles.pillPending}`}>
              <Clock size={10} strokeWidth={2.4} />
              Reconnect needed
            </span>
          ) : (
            <span className={`${styles.pill} ${styles.pillInactive}`}>Revoked</span>
          )}
          {member.is_setup_owner ? (
            <span
              className={`${styles.pill} ${styles.pillNeutral}`}
              title="Paired the device — no special privileges."
            >
              Setup owner
            </span>
          ) : null}
        </div>
      </div>
      <div className={styles.rowActions}>
        {status === "not_connected" || status === "reconnect_needed" ? (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnSmall}`}
            style={{ minHeight: 36 }}
            onClick={onConnectGoogle}
          >
            <LogIn size={14} strokeWidth={2.4} />
            Connect Google
          </button>
        ) : null}
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={`Edit ${member.name}`}
          onClick={onEdit}
        >
          <Pencil size={16} strokeWidth={2} />
        </button>
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={`Set ${member.name} inactive`}
          onClick={onSetInactive}
          title="Set inactive"
        >
          <MoreHorizontal size={16} strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}

function CarRow({
  car,
  onEdit,
  onSetInactive,
  onDelete,
}: {
  car: CarResponse;
  onEdit: () => void;
  onSetInactive: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className={styles.memberRow}>
      <CarAvatar color={car.color} size="lg" />
      <div className={styles.memberInfo}>
        <div className={styles.memberName}>{car.name}</div>
        <div className={styles.memberMeta}>
          <span>
            {car.year ? `${car.year} · ` : ""}
            {car.color_label ?? car.notes ?? "Active"}
          </span>
        </div>
      </div>
      <div className={styles.rowActions} style={{ position: "relative" }}>
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={m.settings_car_edit_aria({ name: car.name })}
          onClick={onEdit}
        >
          <Pencil size={16} strokeWidth={2} />
        </button>
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={m.settings_car_more_aria({ name: car.name })}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <MoreHorizontal size={16} strokeWidth={2} />
        </button>
        {menuOpen ? (
          <div
            role="menu"
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              right: 0,
              background: "var(--card)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--fridge-radius)",
              boxShadow: "var(--shadow-md)",
              minWidth: 180,
              padding: 6,
              zIndex: 20,
            }}
          >
            <button
              role="menuitem"
              type="button"
              className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
              style={{ width: "100%", justifyContent: "flex-start" }}
              onClick={() => {
                setMenuOpen(false);
                onSetInactive();
              }}
            >
              {m.settings_car_set_inactive()}
            </button>
            <button
              role="menuitem"
              type="button"
              className={`${styles.btn} ${styles.btnSmall} ${styles.btnDestructive}`}
              style={{ width: "100%", justifyContent: "flex-start", marginTop: 4 }}
              onClick={() => {
                setMenuOpen(false);
                onDelete();
              }}
            >
              {m.settings_car_delete_permanently()}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function PreferencesPanel({
  prefs,
  onChange,
}: {
  prefs: FamilyPreferencesResponse;
  onChange: (patch: Partial<FamilyPreferencesResponse>) => Promise<void> | void;
}) {
  const intervalMinutes = Math.round(prefs.sync_interval_sec / 60);
  return (
    <div>
      <div className={styles.prefRow}>
        <div className={styles.prefLabel}>
          <div className="lt">{m.prefs_sync_interval_label()}</div>
          <div className="ls">{m.prefs_sync_interval_sub()}</div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {([1, 5, 15] as const).map((mins) => (
            <button
              key={mins}
              type="button"
              onClick={() => void onChange({ sync_interval_sec: mins * 60 })}
              className={`${styles.btn} ${styles.btnSmall} ${
                intervalMinutes === mins ? styles.btnPrimary : styles.btnGhost
              }`}
              aria-pressed={intervalMinutes === mins}
            >
              {m.prefs_sync_minutes({ count: mins })}
            </button>
          ))}
        </div>
      </div>

      <PrefToggleRow
        title={m.prefs_fanout_label()}
        sub={m.prefs_fanout_sub()}
        value={prefs.fanout_enabled}
        onChange={(v) => void onChange({ fanout_enabled: v })}
      />
      <PrefToggleRow
        title={m.prefs_voice_wake_label()}
        sub={m.prefs_voice_wake_sub()}
        value={prefs.voice_wake_enabled}
        onChange={(v) => void onChange({ voice_wake_enabled: v })}
        disabled
      />
      <PrefToggleRow
        title={m.prefs_always_on_label()}
        sub={m.prefs_always_on_sub()}
        value={prefs.always_on}
        onChange={(v) => void onChange({ always_on: v })}
      />
    </div>
  );
}

function SyncedCalendarsCard({
  members,
  syncStates,
  onPull,
}: {
  members: MemberResponse[];
  syncStates: SyncStateResponse[];
  onPull: (memberId: string) => void;
}) {
  return (
    <div className={styles.settingsCard}>
      <h3>{m.settings_synced_calendars_title()}</h3>
      <div className={styles.sub}>{m.settings_synced_calendars_subtitle()}</div>
      <div className={styles.syncList}>
        {members.map((mem) => {
          const state = syncStates.find((s) => s.member_id === mem.id);
          const status = mem.google.status;
          const label =
            status === "connected"
              ? state?.last_pull_at
                ? m.calendar_sync_label_relative({ value: formatRelative(state.last_pull_at) })
                : m.calendar_sync_label_syncing()
              : status === "not_connected"
              ? m.calendar_sync_label_not_connected()
              : status === "reconnect_needed"
              ? m.calendar_sync_label_reconnect()
              : m.calendar_sync_label_revoked();
          const dotClass =
            status === "connected"
              ? styles.syncOk
              : status === "reconnect_needed"
              ? `${styles.syncOk} ${styles.syncWarn}`
              : status === "not_connected"
              ? `${styles.syncOk} ${styles.syncWarn}`
              : `${styles.syncOk} ${styles.syncErr}`;
          return (
            <div key={mem.id} className={styles.syncRow}>
              <MemberAvatar
                initials={initialsFromName(mem.name)}
                color={mem.color}
                size="md"
              />
              <div className={styles.name}>{mem.name}</div>
              <div className={styles.last}>{label}</div>
              <button
                type="button"
                aria-label={m.calendar_sync_now_aria({ name: mem.name })}
                onClick={() => onPull(mem.id)}
                disabled={status !== "connected"}
                className={styles.iconBtn}
                style={{ width: 32, height: 32, opacity: status === "connected" ? 1 : 0.5 }}
              >
                <RefreshCw size={14} strokeWidth={2.2} />
              </button>
              <span className={dotClass} title={m.calendar_sync_status_title({ status })} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.round(ms / 60_000);
  if (min < 1) return m.relative_just_now();
  if (min < 60) return m.relative_minutes({ count: min });
  const hr = Math.round(min / 60);
  if (hr < 24) return m.relative_hours({ count: hr });
  const d = Math.round(hr / 24);
  return m.relative_days({ count: d });
}

function PrefToggleRow({
  title,
  sub,
  value,
  onChange,
  disabled,
}: {
  title: string;
  sub: string;
  value: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className={styles.prefRow}>
      <div className={styles.prefLabel}>
        <div className="lt">{title}</div>
        <div className="ls">{sub}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        aria-label={title}
        disabled={disabled}
        className={`${styles.toggle} ${value ? styles.on : ""}`}
        style={disabled ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
        onClick={() => !disabled && onChange(!value)}
      />
    </div>
  );
}
