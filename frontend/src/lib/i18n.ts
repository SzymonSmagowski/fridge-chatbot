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

const FALLBACK_LOCALE: AppLocale = "en";

/**
 * First-load heuristic — picks Polish only when the browser language clearly
 * starts with "pl"; everything else falls back to English. Paraglide will
 * remember the choice in localStorage from then on.
 */
export function detectInitialLocale(): AppLocale {
  if (typeof navigator === "undefined") return FALLBACK_LOCALE;
  const lang = (navigator.language || "").toLowerCase();
  return lang.startsWith("pl") ? "pl" : FALLBACK_LOCALE;
}
