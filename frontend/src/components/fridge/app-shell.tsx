"use client";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { AmbientLayer } from "./ambient-layer";
import { BottomTabNav, type TabKey } from "./bottom-tab-nav";
import { CalendarView } from "./calendar-view";
import { ChatView } from "./chat-view";
import { NotesView } from "./notes-view";
import { SettingsView } from "./settings-view";
import { StatusBar } from "./status-bar";
import { useFamilyEvents } from "@/lib/use-family-events";
import { maybeStartPerfMonitor } from "@/lib/perf-monitor";
import {
  ApiError,
  carsApi,
  familyApi,
  membersApi,
  type CarResponse,
  type FamilyResponse,
  type MemberResponse,
} from "@/lib/api";
import { m } from "@/paraglide/messages.js";

/**
 * Outer device shell — owns family/members/cars data so each tab gets the
 * same canonical view of these slow-moving lists. Per Architect §5.3/§5.4
 * cache TTL is 15min for members and 5min for cars, so we share via state.
 */
export function FridgeAppShell() {
  const [family, setFamily] = useState<FamilyResponse | null>(null);
  const [members, setMembers] = useState<MemberResponse[]>([]);
  const [cars, setCars] = useState<CarResponse[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [active, setActive] = useState<TabKey>("notes");

  const refresh = useCallback(async () => {
    try {
      const [f, m, c] = await Promise.all([
        familyApi.get(),
        membersApi.list("active"),
        carsApi.list("active"),
      ]);
      setFamily(f);
      setMembers(m);
      setCars(c);
      setLoadError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : m.errors_load_family_failed();
      setLoadError(msg);
      toast.error(msg);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount + refetch when `refresh` identity changes. React 19's
    // `react-hooks/set-state-in-effect` flags this idiom; suppressed because
    // the setState lives inside the awaited fetch callback, not the effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    // Local-dev opt-in: `localStorage.perfMonitor = "1"` then reload.
    maybeStartPerfMonitor();
  }, [refresh]);

  useFamilyEvents(refresh);

  return (
    <div className={styles.fridgeRoot}>
      <AmbientLayer />
      {/* `.appLayer` is the structural "everything that's not the tab bar"
       * wrapper. Modals/sheets/dialogs render inside this subtree; their
       * z-index now plays in the root stacking context (because .appLayer
       * doesn't create one), so they reliably paint above .tabBar. */}
      <div className={styles.appLayer}>
        <StatusBar familyName={family?.name ?? m.app_shell_default_family_name()} />
        {active === "chat" ? <ChatView /> : null}
        {active === "notes" ? <NotesView members={members} cars={cars} /> : null}
        {active === "calendar" ? <CalendarView members={members} cars={cars} /> : null}
        {active === "settings" ? (
          <SettingsView family={family} members={members} cars={cars} refresh={refresh} />
        ) : null}
        {loadError && active !== "settings" ? (
          <div
            style={{
              position: "absolute",
              top: 12,
              left: "50%",
              transform: "translateX(-50%)",
              background: "var(--card)",
              border: "1px solid var(--border-color)",
              color: "var(--destructive)",
              padding: "8px 14px",
              borderRadius: 12,
              fontSize: 13,
              zIndex: 30,
            }}
            role="status"
          >
            {loadError}
          </div>
        ) : null}
      </div>
      <BottomTabNav active={active} onChange={setActive} />
    </div>
  );
}
