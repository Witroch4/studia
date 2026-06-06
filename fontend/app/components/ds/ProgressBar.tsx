"use client";

import React from "react";

const COLORS: Record<string, string> = {
  primary: "var(--color-primary)",
  secondary: "var(--color-secondary)",
  success: "var(--color-success)",
  error: "var(--color-error)",
  warning: "var(--color-warning)",
};

export interface ProgressBarProps {
  value?: number;
  color?: string;
  height?: number;
  style?: React.CSSProperties;
  trackStyle?: React.CSSProperties;
}

/**
 * ProgressBar — thin rounded track + colored fill. Used for stat cards,
 * weekly goals, and the study-mode card-position indicator.
 */
export function ProgressBar({ value = 0, color = "primary", height = 4, style = {}, trackStyle = {} }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value));
  const fill = COLORS[color] || color;
  return (
    <div
      style={{
        width: "100%",
        height: `${height}px`,
        background: "var(--color-gray-700)",
        borderRadius: "var(--radius-full)",
        overflow: "hidden",
        ...trackStyle,
        ...style,
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: fill,
          borderRadius: "var(--radius-full)",
          transition: "width var(--dur-base) var(--ease-out-expo)",
        }}
      />
    </div>
  );
}
