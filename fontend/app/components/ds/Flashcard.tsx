"use client";

import React, { useState } from "react";
import { Badge } from "./Badge";
import { Icon } from "./Icon";

export interface FlashcardProps {
  tema?: string;
  assunto?: string;
  id?: number | string;
  front?: React.ReactNode;
  back?: React.ReactNode;
  flipped?: boolean;
  onFlip?: (flipped: boolean) => void;
  height?: number;
  style?: React.CSSProperties;
}

/**
 * Flashcard — the centerpiece study card with a 3D Y-axis flip.
 * Front shows the question (tema badge + assunto tag); back shows the answer.
 * Uncontrolled by default (click to flip); pass `flipped`+`onFlip` to control.
 */
export function Flashcard({
  tema = "Tema",
  assunto,
  id,
  front,
  back,
  flipped: controlledFlipped,
  onFlip,
  height = 420,
  style = {},
}: FlashcardProps) {
  const [internal, setInternal] = useState(false);
  const flipped = controlledFlipped != null ? controlledFlipped : internal;
  const toggle = () => {
    if (onFlip) onFlip(!flipped);
    if (controlledFlipped == null) setInternal((f) => !f);
  };

  const face: React.CSSProperties = {
    position: "absolute",
    inset: 0,
    width: "100%",
    height: "100%",
    background: "var(--surface-card)",
    border: "1px solid var(--border-default)",
    borderRadius: "var(--radius-2xl)",
    boxShadow: "var(--glow-flashcard)",
    padding: "2rem",
    backfaceVisibility: "hidden",
    WebkitBackfaceVisibility: "hidden",
    display: "flex",
    flexDirection: "column",
  };

  return (
    <div
      onClick={toggle}
      style={{ perspective: "1200px", height: `${height}px`, cursor: "pointer", ...style }}
    >
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          transformStyle: "preserve-3d",
          transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
          transition: "transform var(--dur-flip) var(--ease-flip)",
        }}
      >
        {/* Front */}
        <div style={{ ...face, alignItems: "center", justifyContent: "center" }}>
          <span style={{ position: "absolute", top: "1.25rem", left: "1.25rem" }}>
            <Badge tone="primary" uppercase size="sm">{tema}</Badge>
          </span>
          {id != null && (
            <span style={{ position: "absolute", top: "1.25rem", right: "1.25rem", fontFamily: "var(--font-sans)", fontSize: "0.75rem", color: "var(--text-faint)", fontWeight: 500 }}>
              #{id}
            </span>
          )}
          {assunto && (
            <span style={{ position: "absolute", top: "3.4rem", left: "1.25rem" }}>
              <Badge tone="purple" size="sm">{assunto}</Badge>
            </span>
          )}
          <div
            style={{
              maxWidth: "32rem",
              textAlign: "center",
              marginTop: "1.5rem",
              fontFamily: "var(--font-sans)",
              fontWeight: 500,
              fontSize: "1.5rem",
              lineHeight: 1.5,
              color: "var(--text-strong)",
            }}
          >
            {front}
          </div>
          <div style={{ position: "absolute", bottom: "1.25rem", right: "1.25rem", display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-faint)", fontSize: "0.75rem", fontFamily: "var(--font-sans)" }}>
            <Icon name="touch_app" size={16} />
            Toque para ver a resposta
          </div>
        </div>

        {/* Back */}
        <div style={{ ...face, transform: "rotateY(180deg)", overflowY: "auto" }}>
          <div style={{ fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-primary)", marginBottom: "1rem" }}>
            Resposta
          </div>
          <div style={{ fontFamily: "var(--font-sans)", fontSize: "0.95rem", lineHeight: 1.7, color: "var(--text-body)" }}>
            {back}
          </div>
        </div>
      </div>
    </div>
  );
}
