"use client";

import React from "react";
import { Icon } from "./Icon";

export type IconButtonSize = "sm" | "md" | "lg";
export type IconButtonVariant = "ghost" | "bordered";

export interface IconButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  icon: string;
  size?: IconButtonSize;
  variant?: IconButtonVariant;
  pill?: boolean;
  dot?: boolean;
}

/**
 * IconButton — square icon-only control (notifications, filter, more_vert).
 * Quiet by default; brightens on hover. Optional pulse dot for notifications.
 */
export function IconButton({
  icon,
  size = "md",
  variant = "ghost",
  pill = true,
  dot = false,
  disabled = false,
  title,
  onClick,
  style = {},
  ...rest
}: IconButtonProps) {
  const dims: Record<IconButtonSize, number> = { sm: 32, md: 38, lg: 44 };
  const iconSizes: Record<IconButtonSize, number> = { sm: 18, md: 20, lg: 22 };
  const d = dims[size] || dims.md;

  const variants: Record<IconButtonVariant, React.CSSProperties> = {
    ghost: { background: "transparent", color: "var(--text-muted)", border: "1px solid transparent" },
    bordered: { background: "var(--surface-card)", color: "var(--text-muted)", border: "1px solid var(--border-default)" },
  };
  const v = variants[variant] || variants.ghost;

  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        position: "relative",
        width: `${d}px`,
        height: `${d}px`,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: pill ? "var(--radius-full)" : "var(--radius-md)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        transition: "background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast)",
        ...v,
        ...style,
      }}
      onMouseEnter={(e) => {
        if (disabled) return;
        e.currentTarget.style.background = "var(--color-gray-800)";
        e.currentTarget.style.color = "var(--text-strong)";
        if (variant === "bordered") e.currentTarget.style.borderColor = "var(--tint-primary)";
      }}
      onMouseLeave={(e) => {
        if (disabled) return;
        e.currentTarget.style.background = (v.background as string) ?? "";
        e.currentTarget.style.color = (v.color as string) ?? "";
        e.currentTarget.style.borderColor = (v.border as string).includes("transparent") ? "transparent" : "var(--border-default)";
      }}
      {...rest}
    >
      <Icon name={icon} size={iconSizes[size] || 20} />
      {dot && (
        <span
          style={{
            position: "absolute",
            top: "8px",
            right: "8px",
            width: "8px",
            height: "8px",
            borderRadius: "var(--radius-full)",
            background: "var(--color-secondary)",
          }}
        />
      )}
    </button>
  );
}
