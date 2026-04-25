"use client";
import { useEffect, useRef } from "react";
import styles from "./fridge.module.css";

/**
 * Animated ambient layer behind every view. Drifting blobs + sunbeam + motes.
 * Honors prefers-reduced-motion via the CSS module rule.
 */
export function AmbientLayer() {
  return (
    <>
      <div className={styles.ambient} aria-hidden="true">
        <div className={`${styles.blob} ${styles.blob1}`} />
        <div className={`${styles.blob} ${styles.blob2}`} />
        <div className={`${styles.blob} ${styles.blob3}`} />
        <div className={`${styles.blob} ${styles.blob4}`} />
        <div className={styles.sunbeam} />
      </div>
      <Motes />
    </>
  );
}

function Motes() {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const mql = typeof window !== "undefined"
      ? window.matchMedia?.("(prefers-reduced-motion: reduce)")
      : null;
    if (mql?.matches) return;

    const timers: number[] = [];
    const spawnMote = () => {
      if (!host.isConnected) return;
      const m = document.createElement("div");
      m.className = styles.mote;
      const size = Math.random() * 5 + 2;
      const startX = Math.random() * 100;
      const startY = 90 + Math.random() * 20;
      const duration = 14000 + Math.random() * 12000;
      const driftX = (Math.random() - 0.5) * 140;
      const driftY = -(200 + Math.random() * 260);
      m.style.width = `${size}px`;
      m.style.height = `${size}px`;
      m.style.left = `${startX}%`;
      m.style.top = `${startY}%`;
      m.style.setProperty("--mx", `${driftX}px`);
      m.style.setProperty("--my", `${driftY}px`);
      m.style.animation = `moteFloat ${duration}ms linear forwards`;
      host.appendChild(m);
      const t = window.setTimeout(() => m.remove(), duration + 50);
      timers.push(t);
    };

    for (let i = 0; i < 16; i++) {
      timers.push(window.setTimeout(spawnMote, i * 600));
    }
    const interval = window.setInterval(spawnMote, 900);

    return () => {
      window.clearInterval(interval);
      timers.forEach(window.clearTimeout);
      host.replaceChildren();
    };
  }, []);

  return <div ref={hostRef} className={styles.motes} aria-hidden="true" />;
}
