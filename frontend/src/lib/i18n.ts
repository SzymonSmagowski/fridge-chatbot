/**
 * i18n helpers — thin wrapper over Paraglide's runtime so callers can stay
 * decoupled from the generated module path. Uses Paraglide's localStorage
 * strategy to persist the selected locale across reloads.
 *
 * TODO: when multi-device pairing lands, mirror the chosen locale into
 * `family_preferences.language` so the kiosk picks it up server-side too.
 */
import {
  getLocale as paraglideGetLocale,
  setLocale as paraglideSetLocale,
  locales,
  type Locale,
} from "@/paraglide/runtime.js";

export type AppLocale = Locale;

export const APP_LOCALES = locales;

export function getCurrentLocale(): AppLocale {
  return paraglideGetLocale() as AppLocale;
}

/**
 * Switch the UI locale. Defaults to reloading the page — Paraglide's `m.*`
 * functions are pure module reads, so a reload is the cleanest way to flip
 * every translated string in the tree at once. The kiosk only switches
 * languages a handful of times in its lifetime, so the cost is negligible.
 */
export function setAppLocale(next: AppLocale, options: { reload?: boolean } = {}) {
  paraglideSetLocale(next, { reload: options.reload ?? true });
}

const FALLBACK_LOCALE: AppLocale = "pl";

/**
 * First-load heuristic — Polish-first for fresh kiosks. The fridge ships
 * for Polish-speaking households (60+ parents, voice-first), so a brand-new
 * device defaults to Polish. A browser explicitly reporting English flips
 * back to English; everything else (including missing `navigator`) lands
 * on Polish. The locale switcher in Settings persists overrides via
 * Paraglide's localStorage strategy — this only fires on the very first
 * paint of an unpaired/never-opened kiosk.
 */
export function detectInitialLocale(): AppLocale {
  if (typeof navigator === "undefined") return FALLBACK_LOCALE;
  const lang = (navigator.language || "").toLowerCase();
  return lang.startsWith("en") ? "en" : FALLBACK_LOCALE;
}
