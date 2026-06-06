"use client";

import React from "react";
import { Icon } from "./Icon";

export type ButtonVariant = "primary" | "secondary" | "subtle" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: string;
  iconRight?: string;
  pill?: boolean;
  fullWidth?: boolean;
  type?: "button" | "submit" | "reset";
}

/**
 * Button — studIA's action button.
 * Variants: primary (solid cyan + glow), secondary (surface + border),
 * subtle (muted/quiet), danger (red). Optional leading/trailing icon.
 */
export function Button({
  children,
  variant = "primary",
  size = "md",
  icon,
  iconRight,
  pill = false,
  fullWidth = false,
  disabled = false,
  type = "button",
  onClick,
  style = {},
  ...rest
}: ButtonProps) {
  const sizes: Record<ButtonSize, { padding: string; fontSize: string; gap: string; icon: number }> = {
    sm: { padding: "0.375rem 0.75rem", fontSize: "0.8125rem", gap: "0.375rem", icon: 16 },
    md: { padding: "0.5rem 1rem", fontSize: "0.875rem", gap: "0.5rem", icon: 18 },
    lg: { padding: "0.625rem 1.25rem", fontSize: "0.9375rem", gap: "0.5rem", icon: 20 },
  };
  const s = sizes[size] || sizes.md;

  const variants: Record<ButtonVariant, React.CSSProperties> = {
    primary: {
      background: "var(--color-primary)",
      color: "var(--text-on-primary)",
      border: "1px solid transparent",
      boxShadow: "var(--glow-primary)",
    },
    secondary: {
      background: "var(--surface-card)",
      color: "var(--text-body)",
      border: "1px solid var(--border-strong)",
      boxShadow: "none",
    },
    subtle: {
      background: "transparent",
      color: "var(--text-muted)",
      border: "1px solid var(--border-default)",
      boxShadow: "none",
    },
    danger: {
      background: "var(--color-error)",
      color: "#fff",
      border: "1px solid transparent",
      boxShadow: "none",
    },
  };
  const v = variants[variant] || variants.primary;

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: s.gap,
        padding: s.padding,
        width: fullWidth ? "100%" : "auto",
        fontFamily: "var(--font-sans)",
        fontWeight: 500,
        fontSize: s.fontSize,
        lineHeight: 1.2,
        borderRadius: pill ? "var(--radius-full)" : "var(--radius-md)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        whiteSpace: "nowrap",
        transition: "background var(--dur-fast), border-color var(--dur-fast), box-shadow var(--dur-fast), opacity var(--dur-fast)",
        ...v,
        ...style,
      }}
      onMouseEnter={(e) => {
        if (disabled) return;
        if (variant === "primary") e.currentTarget.style.background = "var(--color-primary-600)";
        else if (variant === "secondary" || variant === "subtle") e.currentTarget.style.background = "var(--color-gray-800)";
        else if (variant === "danger") e.currentTarget.style.filter = "brightness(0.92)";
      }}
      onMouseLeave={(e) => {
        if (disabled) return;
        e.currentTarget.style.background = (v.background as string) ?? "";
        e.currentTarget.style.filter = "none";
      }}
      {...rest}
    >
      {icon && <Icon name={icon} size={s.icon} />}
      {children}
      {iconRight && <Icon name={iconRight} size={s.icon} />}
    </button>
  );
}
