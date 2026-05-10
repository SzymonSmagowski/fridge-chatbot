"use client";

import styles from "./fridge.module.css";
import { familyApi } from "@/lib/api";
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
 * Two-button language toggle for the Settings tab.
 *
 * Owns *both* the kiosk UI locale (via Paraglide localStorage) and the
 * household's assistant default (`family_preferences.voice_locale`). Tying
 * them together is deliberate: users overwhelmingly expect "switch to
 * Polish" to mean every part of the experience flips, not just the labels.
 * Per-turn language detection inside the LangGraph still flips on clear
 * opposite-language input, so a Polish-pinned household with an English-
 * speaking guest still gets English replies for that guest's turns.
 *
 * The voice_locale write is best-effort fire-and-forget — if it fails
 * (offline, transient API issue), the UI locale still flips so the user
 * isn't stuck with the wrong labels. The next session will read the old
 * voice_locale from the DB.
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
              if (isActive) return;
              setAppLocale(opt.code);
              // Mirror to family_preferences so the voice agent's default
              // language (and greeting) follows the kiosk UI. Fire-and-
              // forget — the UI locale change above is the user-visible
              // signal that the click registered; an API error here
              // shouldn't block it.
              void familyApi
                .patchPreferences({ voice_locale: opt.code })
                .catch((err) => {
                  console.warn(
                    "[language] failed to mirror UI locale to voice_locale:",
                    err,
                  );
                });
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
