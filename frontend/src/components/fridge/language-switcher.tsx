"use client";

import styles from "./fridge.module.css";
import { getCurrentLocale, setAppLocale, type AppLocale } from "@/lib/i18n";
import { m } from "@/paraglide/messages.js";

interface LangOption {
  code: AppLocale;
  flag: string;
  label: () => string;
}

const OPTIONS: LangOption[] = [
  { code: "en", flag: "🇬🇧", label: () => m.language_english() },
  { code: "pl", flag: "🇵🇱", label: () => m.language_polish() },
];

/**
 * Two-button language toggle for the Settings tab. Persists via Paraglide's
 * localStorage strategy and reloads the page on switch so every `m.*()` call
 * picks up the new locale at once.
 */
export function LanguageSwitcher() {
  const current = getCurrentLocale();
  return (
    <div
      className={styles.langSwitch}
      role="radiogroup"
      aria-label={m.language_aria()}
    >
      {OPTIONS.map((opt) => {
        const isActive = opt.code === current;
        return (
          <button
            key={opt.code}
            type="button"
            role="radio"
            aria-checked={isActive}
            className={`${styles.langOption} ${isActive ? styles.langOptionActive : ""}`}
            onClick={() => {
              if (!isActive) setAppLocale(opt.code);
            }}
          >
            <span aria-hidden="true">{opt.flag}</span>
            <span>{opt.label()}</span>
          </button>
        );
      })}
    </div>
  );
}
