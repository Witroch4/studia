"use client";

import React, { useState } from "react";
import { ProgressBar } from "./ProgressBar";

const ICON_COLORS: Record<string, string> = {
  primary: "var(--color-primary)",
  secondary: "var(--color-secondary)",
  success: "var(--color-success)",
  error: "var(--color-error)",
  warning: "var(--color-warning)",
};

export interface StatCardProps {
  title: string;
  icon?: string;
  iconColor?: string;
  progress?: number;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * StatCard — dashboard metric tile. A faded icon watermark floats top-right
 * (10%→20% on hover); content sits left; a thin progress bar pins the bottom.
 */
export function StatCard({ title, icon, iconColor = "primary", progress, children, style = {} }: StatCardProps) {
  const [hovered, setHovered] = useState(false);
  const accent = ICON_COLORS[iconColor] || iconColor;
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        overflow: "hidden",
        background: "var(--surface-card)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--pad-card)",
        boxShadow: "var(--shadow-sm)",
        ...style,
      }}
    >
      {icon && (
        <span
          className="material-symbols-outlined"
          style={{
            position: "absolute",
            top: "0.75rem",
            right: "0.75rem",
            fontSize: "60px",
            color: accent,
            opacity: hovered ? 0.2 : 0.1,
            transition: "opacity var(--dur-base)",
            pointerEvents: "none",
          }}
        >
          {icon}
        </span>
      )}
      <h3
        style={{
          margin: 0,
          fontFamily: "var(--font-sans)",
          fontWeight: 600,
          fontSize: "0.75rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--text-muted)",
          marginBottom: "0.5rem",
        }}
      >
        {title}
      </h3>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "0.5rem", minHeight: "2.5rem" }}>{children}</div>
      {progress != null && (
        <div style={{ marginTop: "1rem" }}>
          <ProgressBar value={progress} color={iconColor} />
        </div>
      )}
    </div>
  );
}
