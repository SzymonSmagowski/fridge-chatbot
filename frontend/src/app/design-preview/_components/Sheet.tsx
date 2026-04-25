"use client";
import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import styles from "../preview.module.css";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Lightweight right-anchored sheet for the preview. In production, swap for
 * shadcn's <Sheet> (components/ui/sheet.tsx) — it uses @base-ui-components/react
 * under the hood and supports focus trap / ESC / scroll lock out of the box.
 */
export function Sheet({ open, onClose, title, children, footer }: SheetProps) {
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
            aria-label="Close"
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
