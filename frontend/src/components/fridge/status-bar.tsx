"use client";
import { useEffect, useState } from "react";
import styles from "./fridge.module.css";
import { formatDateTime } from "@/lib/intl";
import { m } from "@/paraglide/messages.js";

export interface StatusBarProps {
  familyName: string;
  paired?: boolean;
}

export function StatusBar({ familyName, paired = true }: StatusBarProps) {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    // Initializing the clock on mount is a deliberate "sync with external
    // system (wall clock)" pattern; the alternative of computing in render
    // causes SSR/hydration mismatch on every request.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNow(new Date());
    const t = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(t);
  }, []);

  const label = now
    ? `${formatDateTime(now, { weekday: "long" })}, ${formatDateTime(now, { month: "long", day: "numeric" })} · ${formatDateTime(now, { hour: "numeric", minute: "2-digit" })}`
    : "";

  return (
    <div className={styles.statusBar} role="status" aria-live="off">
      <div>
        <span className={styles.statusDot} aria-hidden="true" />
        {label}
      </div>
      <div>
        {familyName}
        {paired ? ` · ${m.app_shell_paired()}` : ""}
      </div>
    </div>
  );
}
