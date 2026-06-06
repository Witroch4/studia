"use client";

import React, { useState } from "react";
import { Icon } from "./Icon";

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "style"> {
  icon?: string;
  label?: string;
  surface?: "card" | "page";
  style?: React.CSSProperties;
  inputStyle?: React.CSSProperties;
}

/**
 * Input — text field on a charcoal/abyss surface with an ember border and a
 * cyan focus ring. Optional leading icon (e.g. search). Supports a `label`.
 */
export function Input({
  icon,
  label,
  type = "text",
  placeholder,
  value,
  defaultValue,
  onChange,
  disabled = false,
  surface = "card",
  style = {},
  inputStyle = {},
  ...rest
}: InputProps) {
  const [focused, setFocused] = useState(false);
  const bg = surface === "page" ? "var(--surface-page)" : "var(--surface-card)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", ...style }}>
      {label && (
        <label
          style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 600,
            fontSize: "0.7rem",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: "var(--text-muted)",
          }}
        >
          {label}
        </label>
      )}
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        {icon && (
          <span style={{ position: "absolute", left: "0.75rem", display: "flex", color: "var(--text-faint)", pointerEvents: "none" }}>
            <Icon name={icon} size={20} />
          </span>
        )}
        <input
          type={type}
          placeholder={placeholder}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
          disabled={disabled}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            width: "100%",
            padding: icon ? "0.625rem 1rem 0.625rem 2.5rem" : "0.625rem 1rem",
            background: bg,
            color: "var(--text-strong)",
            fontFamily: "var(--font-sans)",
            fontSize: "0.875rem",
            border: `1px solid ${focused ? "var(--color-primary)" : "var(--border-default)"}`,
            borderRadius: "var(--radius-md)",
            outline: "none",
            boxShadow: focused ? "0 0 0 1px var(--color-primary)" : "none",
            transition: "border-color var(--dur-fast), box-shadow var(--dur-fast)",
            opacity: disabled ? 0.5 : 1,
            ...inputStyle,
          }}
          {...rest}
        />
      </div>
    </div>
  );
}
