"use client";
import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

export interface FridgeSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Right-anchored sheet matching the design tokens. Uses the scoped CSS module
 * so styles don't depend on shadcn/Tailwind. ESC closes; body scroll locked
 * while open. Click on overlay closes.
 */
export function FridgeSheet({ open, onClose, title, children, footer }: FridgeSheetProps) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className={styles.sheetOverlay}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <aside
        className={styles.sheetPanel}
        onClick={(e) => e.stopPropagation()}
      >
        <header className={styles.sheetHeader}>
          <h3>{title}</h3>
          <button
            type="button"
            className={styles.sheetClose}
            aria-label={m.common_close()}
            onClick={onClose}
          >
            <X size={18} strokeWidth={2} />
          </button>
        </header>
        <div className={styles.sheetBody}>{children}</div>
        {footer ? <footer className={styles.sheetFooter}>{footer}</footer> : null}
      </aside>
    </div>
  );
}
