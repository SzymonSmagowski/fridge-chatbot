"use client";
import type { CSSProperties } from "react";
import { Car as CarIcon } from "lucide-react";
import styles from "../preview.module.css";
import { MEMBER_COLOR_HEX, type MemberColor } from "./types";

type Size = "sm" | "md" | "lg" | "xl";

export interface CarAvatarProps {
  color: MemberColor;
  size?: Size;
  title?: string;
  className?: string;
}

const SIZE_CLASS: Record<Size, string> = {
  sm: styles.avatarSm,
  md: "",
  lg: styles.avatarLg,
  xl: styles.avatarXl,
};

const ICON_SIZE: Record<Size, number> = { sm: 12, md: 16, lg: 22, xl: 28 };

export function CarAvatar({ color, size = "md", title, className }: CarAvatarProps) {
  const style: CSSProperties = { background: MEMBER_COLOR_HEX[color] };
  const classes = [styles.avatar, SIZE_CLASS[size], className].filter(Boolean).join(" ");
  return (
    <span className={classes} style={style} title={title} aria-label={title ?? "Car"}>
      <CarIcon size={ICON_SIZE[size]} strokeWidth={2} />
    </span>
  );
}
