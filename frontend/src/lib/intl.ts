/**
 * Locale-aware Intl wrappers — keeps every Date-/Number-formatting call in
 * one place so we never accidentally render `Mon, Apr 25` to a Polish user.
 */
import { getCurrentLocale } from "@/lib/i18n";

const LOCALE_TAG: Record<string, string> = {
  en: "en-US",
  pl: "pl-PL",
};

function tag(): string {
  return LOCALE_TAG[getCurrentLocale()] ?? "en-US";
}

export function formatDateTime(d: Date, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(tag(), options).format(d);
}

export function formatNumber(n: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(tag(), options).format(n);
}
