"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { detectInitialLocale } from "@/lib/i18n";

const LOCALE_STORAGE_KEY = "PARAGLIDE_LOCALE";

/**
 * On first visit, picks an initial locale from `navigator.language` and
 * persists it to Paraglide's localStorage key. Subsequent visits read the
 * stored value directly via Paraglide's strategy chain — no re-render needed
 * because `m.*()` calls read the live locale on each invocation.
 *
 * The first paint after `localStorage.setItem` still uses `baseLocale` (pl)
 * because Paraglide's getter cached the value before the seed. We trigger a
 * single reload so English-browser users see English from the second paint on.
 * Polish-browser users (the common case) skip the reload entirely.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const hasReloaded = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (hasReloaded.current) return;
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored) return;
    const initial = detectInitialLocale();
    window.localStorage.setItem(LOCALE_STORAGE_KEY, initial);
    if (initial !== "pl") {
      hasReloaded.current = true;
      window.location.reload();
    }
  }, []);

  return <>{children}</>;
}
