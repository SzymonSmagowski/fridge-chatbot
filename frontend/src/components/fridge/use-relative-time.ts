"use client";
import { m } from "@/paraglide/messages.js";

export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = now.getTime() - then;
  if (diffMs < 60_000) return m.relative_just_now();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return m.relative_minutes({ count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return m.relative_hours({ count: hours });
  const days = Math.floor(hours / 24);
  return m.relative_days({ count: days });
}
