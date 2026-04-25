"use client";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

export function NotesSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className={styles.skeletonGrid} aria-busy="true" aria-label={m.notes_skeleton_aria()}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={styles.skeletonCard} />
      ))}
    </div>
  );
}
