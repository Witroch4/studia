"use client";

import React, { useState } from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  pad?: boolean;
  hover?: boolean;
  dashed?: boolean;
  accent?: boolean;
}

/**
 * Card — the studIA surface container: charcoal bg, ember border, 12px radius,
 * quiet shadow. Hover can lift the border to cyan. Use `pad={false}` to lay out
 * your own header/body/footer regions.
 */
export function Card({
  children,
  pad = true,
  hover = false,
  dashed = false,
  accent = false,
  style = {},
  onClick,
  ...rest
}: CardProps) {
  const [hovered, setHovered] = useState(false);
  const borderColor = dashed
    ? hovered && hover ? "var(--color-primary)" : "var(--color-gray-700)"
    : accent ? "rgba(6,182,212,0.3)"
    : hovered && hover ? "var(--tint-primary)" : "var(--border-default)";
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: "var(--surface-card)",
        border: `1px ${dashed ? "dashed" : "solid"} ${borderColor}`,
        borderRadius: "var(--radius-lg)",
        padding: pad ? "var(--pad-card)" : 0,
        boxShadow: hover && hovered ? "var(--shadow-md)" : "var(--shadow-sm)",
        transition: "border-color var(--dur-base), box-shadow var(--dur-base)",
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
