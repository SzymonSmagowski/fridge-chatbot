"use client";
import {
  Calendar,
  Car,
  FileText,
  Key,
  Package,
  PartyPopper,
  Pill,
  ShoppingCart,
  Trash2,
  Utensils,
} from "lucide-react";
import type { ReactElement } from "react";

export type NoteIconName =
  | "shopping-cart"
  | "trash-2"
  | "file-text"
  | "calendar"
  | "car"
  | "package"
  | "utensils"
  | "party"
  | "pill"
  | "key";

export const NOTE_ICONS: NoteIconName[] = [
  "shopping-cart",
  "trash-2",
  "file-text",
  "calendar",
  "car",
  "package",
  "utensils",
  "party",
  "pill",
  "key",
];

export function renderNoteIcon(
  name: string | null | undefined,
  size = 18,
): ReactElement | null {
  switch (name) {
    case "shopping-cart":
      return <ShoppingCart size={size} strokeWidth={2} />;
    case "trash-2":
      return <Trash2 size={size} strokeWidth={2} />;
    case "file-text":
      return <FileText size={size} strokeWidth={2} />;
    case "calendar":
      return <Calendar size={size} strokeWidth={2} />;
    case "car":
      return <Car size={size} strokeWidth={2} />;
    case "package":
      return <Package size={size} strokeWidth={2} />;
    case "utensils":
      return <Utensils size={size} strokeWidth={2} />;
    case "party":
      return <PartyPopper size={size} strokeWidth={2} />;
    case "pill":
      return <Pill size={size} strokeWidth={2} />;
    case "key":
      return <Key size={size} strokeWidth={2} />;
    default:
      return null;
  }
}
