"use client";

import React from "react";
import { Icon } from "./Icon";

export type BadgeTone =
  | "primary"
  | "secondary"
  | "success"
  | "error"
  | "warning"
  | "neutral"
  | "purple";

const TONES: Record<BadgeTone, { fg: string; bg: string }> = {
  primary: { fg: "var(--color-primary)", bg: "var(--tint-primary)" },
  secondary: { fg: "#c4b5fd", bg: "var(--tint-secondary)" },
  success: { fg: "var(--color-success)", bg: "var(--tint-success)" },
  error: { fg: "var(--color-error)", bg: "var(--tint-error)" },
  warning: { fg: "var(--color-warning)", bg: "var(--tint-warning)" },
  neutral: { fg: "var(--text-muted)", bg: "var(--tint-neutral)" },
  purple: { fg: "#c084fc", bg: "rgba(168,85,247,0.12)" },
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  icon?: string;
  size?: "sm" | "md";
  uppercase?: boolean;
}

/**
 * Badge — small pill with a translucent tinted background and matching text.
 * The studIA signature: color washed over dark, not a solid fill.
 */
export function Badge({
  children,
  tone = "primary",
  icon,
  size = "md",
  uppercase = false,
  style = {},
  ...rest
}: BadgeProps) {
  const t = TONES[tone] || TONES.primary;
  const sizes = {
    sm: { padding: "0.125rem 0.5rem", fontSize: "0.65rem", gap: "0.25rem", icon: 12 },
    md: { padding: "0.25rem 0.625rem", fontSize: "0.75rem", gap: "0.3rem", icon: 14 },
  } as const;
  const s = sizes[size] || sizes.md;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: s.gap,
        padding: s.padding,
        background: t.bg,
        color: t.fg,
        borderRadius: "var(--radius-full)",
        fontFamily: "var(--font-sans)",
        fontWeight: 600,
        fontSize: s.fontSize,
        lineHeight: 1.2,
        letterSpacing: uppercase ? "0.05em" : "normal",
        textTransform: uppercase ? "uppercase" : "none",
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {icon && <Icon name={icon} size={s.icon} />}
      {children}
    </span>
  );
}
