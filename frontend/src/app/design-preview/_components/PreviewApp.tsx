"use client";
import { useState } from "react";
import styles from "../preview.module.css";
import { AmbientLayer } from "./AmbientLayer";
import { BottomTabNav, type TabKey } from "./BottomTabNav";
import { CalendarView } from "./CalendarView";
import { ChatView } from "./ChatView";
import { NotesView } from "./NotesView";
import { SettingsView } from "./SettingsView";
import { StatusBar } from "./StatusBar";

/**
 * Client component that owns the active-tab state and renders one feature view
 * at a time. The outer page.tsx is a server component — this is the boundary.
 */
export function PreviewApp() {
  const [active, setActive] = useState<TabKey>("notes");

  return (
    <div className={styles.screen}>
      <AmbientLayer />
      <StatusBar />
      {active === "notes" ? <NotesView /> : null}
      {active === "calendar" ? <CalendarView /> : null}
      {active === "chat" ? <ChatView /> : null}
      {active === "settings" ? <SettingsView /> : null}
      <BottomTabNav active={active} onChange={setActive} />
    </div>
  );
}
