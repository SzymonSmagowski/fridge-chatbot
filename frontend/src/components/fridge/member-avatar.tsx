"use client";
import type { CSSProperties } from "react";
import styles from "./fridge.module.css";
import { MEMBER_COLOR_HEX, type MemberColor } from "./types";

type Size = "sm" | "md" | "lg" | "xl";

export interface MemberAvatarProps {
  initials: string;
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

export function MemberAvatar({
  initials,
  color,
  size = "md",
  title,
  className,
}: MemberAvatarProps) {
  const style: CSSProperties = { background: MEMBER_COLOR_HEX[color] };
  const classes = [styles.avatar, SIZE_CLASS[size], className].filter(Boolean).join(" ");
  return (
    <span className={classes} style={style} title={title} aria-label={title}>
      {initials}
    </span>
  );
}
