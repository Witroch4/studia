"use client";

import React from "react";

export interface ChatBubbleProps {
  role?: "user" | "model";
  children?: React.ReactNode;
  typing?: boolean;
  style?: React.CSSProperties;
}

/**
 * ChatBubble — AulaChat message bubble. User bubbles are cyan-tinted and align
 * right; model (tutor) bubbles are gray-tinted and align left. `typing` shows
 * the three bouncing dots.
 */
export function ChatBubble({ role = "model", children, typing = false, style = {} }: ChatBubbleProps) {
  const isUser = role === "user";
  const align = isUser ? "flex-end" : "flex-start";

  if (typing) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-start", ...style }}>
        <div style={{ background: "rgba(31,41,55,0.5)", borderRadius: "var(--radius-lg)", padding: "0.75rem 1rem", display: "flex", gap: "0.25rem" }}>
          {[0, 150, 300].map((d) => (
            <span
              key={d}
              style={{
                width: 8,
                height: 8,
                borderRadius: "var(--radius-full)",
                background: "rgba(6,182,212,0.5)",
                animation: "cc-bounce 1s infinite",
                animationDelay: `${d}ms`,
                display: "inline-block",
              }}
            />
          ))}
        </div>
        <style>{`@keyframes cc-bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}`}</style>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", justifyContent: align, ...style }}>
      <div
        style={{
          maxWidth: "85%",
          borderRadius: "var(--radius-lg)",
          padding: "0.75rem 1rem",
          fontFamily: "var(--font-sans)",
          fontSize: "0.875rem",
          lineHeight: 1.6,
          background: isUser ? "var(--tint-primary)" : "rgba(31,41,55,0.5)",
          color: isUser ? "var(--text-strong)" : "var(--text-body)",
          whiteSpace: "pre-wrap",
        }}
      >
        {children}
      </div>
    </div>
  );
}
