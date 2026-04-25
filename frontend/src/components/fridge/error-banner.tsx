"use client";
import { AlertCircle } from "lucide-react";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

export interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className={styles.errorBanner} role="alert">
      <AlertCircle size={16} strokeWidth={2} />
      <span>{message}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          {m.common_retry()}
        </button>
      ) : null}
    </div>
  );
}
