"use client";

import React from "react";

const COLORS: Record<string, string> = {
  primary: "var(--color-primary)",
  secondary: "var(--color-secondary)",
  success: "var(--color-success)",
  error: "var(--color-error)",
  blue: "var(--color-deck-blue)",
  orange: "var(--color-deck-orange)",
  red: "var(--color-deck-red)",
  green: "var(--color-deck-green)",
  purple: "var(--color-deck-purple)",
};

export interface CircularProgressProps {
  value?: number;
  size?: number;
  color?: string;
  strokeWidth?: number;
  showLabel?: boolean;
  label?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * CircularProgress — SVG ring with the percentage centered. Used on deck cards.
 * Built on the product's 36-unit viewBox path with stroke-dasharray.
 */
export function CircularProgress({
  value = 0,
  size = 64,
  color = "primary",
  strokeWidth = 3,
  showLabel = true,
  label,
  style = {},
}: CircularProgressProps) {
  const pct = Math.max(0, Math.min(100, value));
  const stroke = COLORS[color] || color;
  return (
    <div style={{ position: "relative", width: size, height: size, ...style }}>
      <svg width={size} height={size} viewBox="0 0 36 36" style={{ transform: "rotate(-90deg)" }}>
        <path
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke="var(--color-gray-700)"
          strokeWidth={strokeWidth}
        />
        <path
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${pct}, 100`}
          style={{ transition: "stroke-dasharray var(--dur-base) var(--ease-out-expo)" }}
        />
      </svg>
      {showLabel && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "var(--font-sans)",
            fontWeight: 700,
            fontSize: `${Math.max(10, size * 0.18)}px`,
            color: "var(--text-strong)",
          }}
        >
          {label != null ? label : `${Math.round(pct)}%`}
        </div>
      )}
    </div>
  );
}
