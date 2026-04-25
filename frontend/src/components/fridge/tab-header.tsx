"use client";
import type { ReactNode } from "react";
import styles from "./fridge.module.css";

export interface TabHeaderProps {
  eyebrow: string;
  title: string;
  right?: ReactNode;
}

export function TabHeader({ eyebrow, title, right }: TabHeaderProps) {
  return (
    <div className={styles.tabHeader}>
      <div className={styles.greeting}>
        <div className={styles.dateLine}>{eyebrow}</div>
        <h2>{title}</h2>
      </div>
      {right ? <div>{right}</div> : null}
    </div>
  );
}
