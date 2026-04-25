"use client";
import { Calendar, FileText, MessageCircle, Settings } from "lucide-react";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

export type TabKey = "chat" | "notes" | "calendar" | "settings";

const ICONS: Record<TabKey, typeof MessageCircle> = {
  chat: MessageCircle,
  notes: FileText,
  calendar: Calendar,
  settings: Settings,
};

export interface BottomTabNavProps {
  active: TabKey;
  onChange: (next: TabKey) => void;
  badges?: Partial<Record<TabKey, number>>;
}

const TAB_KEYS: TabKey[] = ["chat", "notes", "calendar", "settings"];

function tabLabel(key: TabKey): string {
  switch (key) {
    case "chat":
      return m.tab_chat();
    case "notes":
      return m.tab_notes();
    case "calendar":
      return m.tab_calendar();
    case "settings":
      return m.tab_settings();
  }
}

export function BottomTabNav({ active, onChange, badges = {} }: BottomTabNavProps) {
  return (
    <nav className={styles.tabBar} role="tablist" aria-label={m.tablist_aria()}>
      {TAB_KEYS.map((key) => {
        const Icon = ICONS[key];
        const isActive = key === active;
        const badgeCount = badges[key];
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`view-${key}`}
            id={`tab-${key}`}
            className={`${styles.tab} ${isActive ? styles.active : ""}`}
            onClick={() => onChange(key)}
          >
            <span className={styles.tabIcon}>
              <Icon size={22} strokeWidth={2} />
            </span>
            <span>{tabLabel(key)}</span>
            {badgeCount && badgeCount > 0 ? (
              <span className={styles.tabBadge} aria-label={m.tab_badge_aria({ count: badgeCount })}>
                {badgeCount}
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
