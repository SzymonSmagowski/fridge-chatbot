"use client";
import { Calendar, FileText, MessageCircle, Settings } from "lucide-react";
import styles from "../preview.module.css";

export type TabKey = "chat" | "notes" | "calendar" | "settings";

export interface TabItem {
  key: TabKey;
  label: string;
  badge?: number;
}

const ICONS: Record<TabKey, typeof MessageCircle> = {
  chat: MessageCircle,
  notes: FileText,
  calendar: Calendar,
  settings: Settings,
};

const TABS: TabItem[] = [
  { key: "chat", label: "Chat", badge: 2 },
  { key: "notes", label: "Notes", badge: 5 },
  { key: "calendar", label: "Calendar", badge: 3 },
  { key: "settings", label: "Settings" },
];

export interface BottomTabNavProps {
  active: TabKey;
  onChange: (next: TabKey) => void;
}

export function BottomTabNav({ active, onChange }: BottomTabNavProps) {
  return (
    <nav className={styles.tabBar} role="tablist" aria-label="Primary navigation">
      {TABS.map((tab) => {
        const Icon = ICONS[tab.key];
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`view-${tab.key}`}
            id={`tab-${tab.key}`}
            className={`${styles.tab} ${isActive ? styles.active : ""}`}
            onClick={() => onChange(tab.key)}
          >
            <span className={styles.tabIcon}>
              <Icon size={22} strokeWidth={2} />
            </span>
            <span>{tab.label}</span>
            {tab.badge ? (
              <span className={styles.tabBadge} aria-label={`${tab.badge} new`}>
                {tab.badge}
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
