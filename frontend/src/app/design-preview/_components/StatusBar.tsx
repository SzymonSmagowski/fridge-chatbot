"use client";
import { useEffect, useState } from "react";
import styles from "../preview.module.css";
import { MOCK_FAMILY_NAME } from "./mock-data";

export function StatusBar() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(t);
  }, []);

  const dow = now.toLocaleDateString(undefined, { weekday: "long" });
  const mon = now.toLocaleDateString(undefined, { month: "long", day: "numeric" });
  const time = now.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  return (
    <div className={styles.statusBar} role="status" aria-live="off">
      <div>
        <span className={styles.statusDot} aria-hidden="true" />
        {`${dow}, ${mon} · ${time}`}
      </div>
      <div>{MOCK_FAMILY_NAME} · Paired</div>
    </div>
  );
}
