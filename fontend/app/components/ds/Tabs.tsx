"use client";

import React from "react";

export type TabItem = string | { value: string; label: React.ReactNode };

export interface TabsProps {
  tabs?: TabItem[];
  value?: string;
  onChange?: (value: string) => void;
  style?: React.CSSProperties;
}

/**
 * Tabs — underline tab bar (Resumo / Fórmulas / Flashcards). Active tab is
 * cyan with a cyan underline indicator; inactive is muted and brightens on hover.
 * Controlled via `value` + `onChange`.
 */
export function Tabs({ tabs = [], value, onChange, style = {} }: TabsProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: "1.5rem",
        borderBottom: "1px solid var(--border-default)",
        ...style,
      }}
    >
      {tabs.map((tab) => {
        const key = typeof tab === "string" ? tab : tab.value;
        const label = typeof tab === "string" ? tab : tab.label;
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange && onChange(key)}
            style={{
              position: "relative",
              padding: "0.75rem 0",
              background: "none",
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              fontWeight: active ? 600 : 500,
              fontSize: "0.875rem",
              color: active ? "var(--color-primary)" : "var(--text-muted)",
              transition: "color var(--dur-fast)",
            }}
            onMouseEnter={(e) => { if (!active) e.currentTarget.style.color = "var(--text-strong)"; }}
            onMouseLeave={(e) => { if (!active) e.currentTarget.style.color = "var(--text-muted)"; }}
          >
            {label}
            <span
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: "-1px",
                height: "2px",
                background: "var(--color-primary)",
                borderRadius: "var(--radius-full)",
                opacity: active ? 1 : 0,
                transition: "opacity var(--dur-fast)",
              }}
            />
          </button>
        );
      })}
    </div>
  );
}
