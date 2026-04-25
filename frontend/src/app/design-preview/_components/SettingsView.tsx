"use client";
import { Check, Clock, LogIn, MoreHorizontal, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { AddCarSheet } from "./AddCarSheet";
import { AddMemberSheet } from "./AddMemberSheet";
import { CarAvatar } from "./CarAvatar";
import { ConfirmDialog } from "./ConfirmDialog";
import { MemberAvatar } from "./MemberAvatar";
import { TabHeader } from "./TabHeader";
import {
  MOCK_CARS,
  MOCK_FAMILY_CREATED,
  MOCK_FAMILY_INITIAL,
  MOCK_FAMILY_NAME,
  MOCK_MEMBERS,
  MOCK_PREFS,
} from "./mock-data";
import type { Car, FamilyPrefs, Member } from "./types";

export function SettingsView() {
  const [members, setMembers] = useState<Member[]>(MOCK_MEMBERS);
  const [cars, setCars] = useState<Car[]>(MOCK_CARS);
  const [prefs, setPrefs] = useState<FamilyPrefs>(MOCK_PREFS);

  const [memberSheet, setMemberSheet] = useState<
    { mode: "create" } | { mode: "edit"; member: Member } | null
  >(null);
  const [carSheet, setCarSheet] = useState<
    { mode: "create" } | { mode: "edit"; car: Car } | null
  >(null);

  const [confirm, setConfirm] = useState<null | {
    title: string;
    body: string;
    confirmLabel: string;
    destructive?: boolean;
    onConfirm: () => void;
  }>(null);

  const activeMembers = members.filter((m) => m.status === "active");
  const activeCars = cars.filter((c) => c.status === "active");

  const setMemberInactive = (m: Member) => {
    setConfirm({
      title: `Set ${m.name} inactive?`,
      body: `${m.name} will be hidden from assignee pickers. Existing notes and events still show their name and color. You can reactivate at any time.`,
      confirmLabel: "Set inactive",
      destructive: true,
      onConfirm: () => {
        setMembers((prev) =>
          prev.map((x) => (x.id === m.id ? { ...x, status: "inactive", google: "inactive" } : x)),
        );
        setConfirm(null);
      },
    });
  };
  const setCarInactive = (c: Car) => {
    setConfirm({
      title: `Set ${c.name} inactive?`,
      body: `${c.name} will be hidden from assignee pickers. Existing notes and events still show its name. You can reactivate at any time.`,
      confirmLabel: "Set inactive",
      destructive: true,
      onConfirm: () => {
        setCars((prev) => prev.map((x) => (x.id === c.id ? { ...x, status: "inactive" } : x)));
        setConfirm(null);
      },
    });
  };
  const deleteCarPermanently = (c: Car) => {
    setConfirm({
      title: `Delete ${c.name}?`,
      body: `This is permanent. Past notes and events will keep showing "${c.name}" as plain text but will no longer link to a car record.`,
      confirmLabel: "Delete permanently",
      destructive: true,
      onConfirm: () => {
        setCars((prev) => prev.filter((x) => x.id !== c.id));
        setConfirm(null);
      },
    });
  };

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
            <div className={styles.crest}>{MOCK_FAMILY_INITIAL}</div>
            <div className={styles.info}>
              <h3>{MOCK_FAMILY_NAME}</h3>
              <p>
                Paired to this fridge · {activeMembers.length} members · {activeCars.length} cars ·
                created {MOCK_FAMILY_CREATED}
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
              <button type="button" className={`${styles.btn} ${styles.btnSmall} ${styles.btnGhost}`}>
                Rename family
              </button>
            </div>
          </div>

          {/* Members */}
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
              {members
                .filter((m) => m.status === "active")
                .map((m) => (
                  <MemberRow
                    key={m.id}
                    member={m}
                    onEdit={() => setMemberSheet({ mode: "edit", member: m })}
                    onSetInactive={() => setMemberInactive(m)}
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

          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Cars */}
            <div className={styles.settingsCard}>
              <h3>
                Cars
                <span className={`${styles.pill} ${styles.pillNeutral}`}>
                  {activeCars.length} active
                </span>
              </h3>
              <div className={styles.sub}>Shared vehicles — assignable to events and notes.</div>

              <div className={styles.memberList}>
                {cars
                  .filter((c) => c.status === "active")
                  .map((c) => (
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
                Add a car
              </button>
            </div>

            {/* Preferences */}
            <div className={styles.settingsCard}>
              <h3>Preferences</h3>
              <div className={styles.sub}>
                Fridge-level behavior. Changes apply immediately.
              </div>

              <div>
                <div className={styles.prefRow}>
                  <div className={styles.prefLabel}>
                    <div className="lt">Calendar sync interval</div>
                    <div className="ls">How often to poll Google Calendar.</div>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {([1, 5, 15] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() =>
                          setPrefs((p) => ({ ...p, syncIntervalMinutes: m }))
                        }
                        className={`${styles.btn} ${styles.btnSmall} ${
                          prefs.syncIntervalMinutes === m ? styles.btnPrimary : styles.btnGhost
                        }`}
                        aria-pressed={prefs.syncIntervalMinutes === m}
                      >
                        {m}m
                      </button>
                    ))}
                  </div>
                </div>

                <div className={styles.prefRow}>
                  <div className={styles.prefLabel}>
                    <div className="lt">Fan-out family events</div>
                    <div className="ls">
                      Unassigned events push to every connected member.
                    </div>
                  </div>
                  <Toggle
                    value={prefs.fanoutEnabled}
                    onChange={(v) => setPrefs((p) => ({ ...p, fanoutEnabled: v }))}
                    label="Fan-out family events"
                  />
                </div>

                <div className={styles.prefRow}>
                  <div className={styles.prefLabel}>
                    <div className="lt">Voice wake phrase</div>
                    <div className="ls">&quot;Hey Fridge&quot; — coming in v1.1.</div>
                  </div>
                  <Toggle
                    value={prefs.voiceWakeEnabled}
                    onChange={(v) => setPrefs((p) => ({ ...p, voiceWakeEnabled: v }))}
                    disabled
                    label="Voice wake (deferred)"
                  />
                </div>

                <div className={styles.prefRow}>
                  <div className={styles.prefLabel}>
                    <div className="lt">Always-on display</div>
                    <div className="ls">Never sleep — screen stays lit 24/7.</div>
                  </div>
                  <Toggle
                    value={prefs.alwaysOn}
                    onChange={(v) => setPrefs((p) => ({ ...p, alwaysOn: v }))}
                    label="Always-on display"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <AddMemberSheet
        state={memberSheet}
        onClose={() => setMemberSheet(null)}
        onSave={(next) => {
          if (memberSheet?.mode === "edit") {
            setMembers((prev) => prev.map((x) => (x.id === next.id ? next : x)));
          } else {
            setMembers((prev) => [...prev, next]);
          }
          setMemberSheet(null);
        }}
      />

      <AddCarSheet
        state={carSheet}
        onClose={() => setCarSheet(null)}
        onSave={(next) => {
          if (carSheet?.mode === "edit") {
            setCars((prev) => prev.map((x) => (x.id === next.id ? next : x)));
          } else {
            setCars((prev) => [...prev, next]);
          }
          setCarSheet(null);
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
    </section>
  );
}

function MemberRow({
  member,
  onEdit,
  onSetInactive,
}: {
  member: Member;
  onEdit: () => void;
  onSetInactive: () => void;
}) {
  return (
    <div className={styles.memberRow}>
      <MemberAvatar initials={member.initials} color={member.color} size="lg" />
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
          {member.email ? <span>{member.email}</span> : null}
          {member.google === "connected" ? (
            <span className={`${styles.pill} ${styles.pillConnected}`}>
              <Check size={10} strokeWidth={3} />
              Google synced
            </span>
          ) : member.google === "pending" ? (
            <span className={`${styles.pill} ${styles.pillPending}`}>
              <Clock size={10} strokeWidth={2.4} />
              No Google account yet
            </span>
          ) : member.google === "reconnect-needed" ? (
            <span className={`${styles.pill} ${styles.pillPending}`}>
              <Clock size={10} strokeWidth={2.4} />
              Reconnect needed
            </span>
          ) : null}
          {member.isSetupOwner ? (
            <span
              className={`${styles.pill} ${styles.pillNeutral}`}
              title="Paired the device — no special privileges."
            >
              Setup owner
            </span>
          ) : null}
          {member.google !== "connected" && !member.email ? (
            <span style={{ color: "var(--muted-fg)" }}>Assignee only</span>
          ) : null}
        </div>
      </div>
      <div className={styles.rowActions}>
        {member.google === "pending" ? (
          <button type="button" className={`${styles.btn} ${styles.btnSmall}`} style={{ minHeight: 36 }}>
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
          aria-label={`More actions for ${member.name}`}
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
  car: Car;
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
            {car.colorLabel ?? car.notes ?? "Active"}
          </span>
        </div>
      </div>
      <div className={styles.rowActions} style={{ position: "relative" }}>
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={`Edit ${car.name}`}
          onClick={onEdit}
        >
          <Pencil size={16} strokeWidth={2} />
        </button>
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={`More actions for ${car.name}`}
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
              borderRadius: "var(--radius)",
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
              Set inactive
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
              Delete permanently
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Toggle({
  value,
  onChange,
  disabled,
  label,
}: {
  value: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      aria-label={label}
      disabled={disabled}
      className={`${styles.toggle} ${value ? styles.on : ""}`}
      style={disabled ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
      onClick={() => !disabled && onChange(!value)}
    />
  );
}
