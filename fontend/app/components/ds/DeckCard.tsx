"use client";

import React, { useState } from "react";
import { Icon } from "./Icon";
import { IconButton } from "./IconButton";
import { CircularProgress } from "./CircularProgress";

export type DeckHue = "cyan" | "blue" | "orange" | "red" | "green" | "purple";

const DECK_HUES: Record<DeckHue, { icon: string; color: string; tint: string; btn: string; btnHover: string }> = {
  cyan: { icon: "school", color: "var(--color-primary)", tint: "var(--tint-primary-soft)", btn: "var(--color-primary)", btnHover: "var(--color-primary-600)" },
  blue: { icon: "functions", color: "var(--color-deck-blue)", tint: "rgba(59,130,246,0.10)", btn: "#2563eb", btnHover: "#1d4ed8" },
  orange: { icon: "architecture", color: "var(--color-deck-orange)", tint: "rgba(249,115,22,0.10)", btn: "#ea580c", btnHover: "#c2410c" },
  red: { icon: "whatshot", color: "var(--color-deck-red)", tint: "rgba(239,68,68,0.10)", btn: "#dc2626", btnHover: "#b91c1c" },
  green: { icon: "bolt", color: "var(--color-deck-green)", tint: "rgba(34,197,94,0.10)", btn: "#16a34a", btnHover: "#15803d" },
  purple: { icon: "science", color: "var(--color-deck-purple)", tint: "rgba(168,85,247,0.10)", btn: "#9333ea", btnHover: "#7e22ce" },
};

export interface DeckCardProps {
  name: string;
  total?: number;
  revisar?: number;
  pct?: number;
  hue?: DeckHue;
  onStudy?: () => void;
  onMenu?: () => void;
  style?: React.CSSProperties;
}

/**
 * DeckCard — a flashcard-library tile: colored icon badge, title, total +
 * "revisar hoje" stats, a circular progress ring, and a footer CTA. When
 * `revisar` is 0 the footer becomes the quiet "Tudo em dia" state.
 */
export function DeckCard({ name, total = 0, revisar = 0, pct = 0, hue = "cyan", onStudy, onMenu, style = {} }: DeckCardProps) {
  const [hovered, setHovered] = useState(false);
  const [btnHover, setBtnHover] = useState(false);
  const h = DECK_HUES[hue] || DECK_HUES.cyan;
  const done = revisar === 0;
  const ringColor = ({ cyan: "primary", blue: "blue", orange: "orange", red: "red", green: "green", purple: "purple" } as const)[hue] || "primary";

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        flexDirection: "column",
        background: "var(--surface-card)",
        border: `1px solid ${hovered ? "var(--tint-primary)" : "var(--border-default)"}`,
        borderRadius: "var(--radius-lg)",
        boxShadow: hovered ? "var(--shadow-md)" : "var(--shadow-sm)",
        transition: "border-color var(--dur-base), box-shadow var(--dur-base)",
        ...style,
      }}
    >
      <div style={{ padding: "var(--pad-card)", flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
          <div style={{ width: 40, height: 40, borderRadius: "var(--radius-md)", background: h.tint, display: "flex", alignItems: "center", justifyContent: "center", color: h.color }}>
            <Icon name={h.icon} size={22} />
          </div>
          {onMenu && <IconButton icon="more_vert" size="sm" onClick={onMenu} />}
        </div>

        <h3 style={{ margin: 0, fontFamily: "var(--font-sans)", fontWeight: 700, fontSize: "1.125rem", color: "var(--text-strong)", marginBottom: "0.25rem" }}>{name}</h3>
        <p style={{ margin: 0, fontFamily: "var(--font-sans)", fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "1.5rem" }}>{total} cartões</p>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <Stat label="Total de Cartões" value={total} />
            <Stat label="Para Revisar Hoje" value={revisar} accent={revisar > 0} />
          </div>
          <CircularProgress value={pct} color={ringColor} size={64} />
        </div>
      </div>

      <div style={{ padding: "1rem", borderTop: "1px solid var(--border-default)", background: "var(--surface-inset)", borderRadius: "0 0 var(--radius-lg) var(--radius-lg)" }}>
        {done ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", padding: "0.5rem", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-md)", color: "var(--text-faint)", fontFamily: "var(--font-sans)", fontWeight: 500, fontSize: "0.875rem" }}>
            <Icon name="check" size={18} />
            Tudo em dia
          </div>
        ) : (
          <button
            type="button"
            onClick={onStudy}
            onMouseEnter={() => setBtnHover(true)}
            onMouseLeave={() => setBtnHover(false)}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.5rem",
              padding: "0.5rem",
              border: "none",
              borderRadius: "var(--radius-md)",
              background: btnHover ? h.btnHover : h.btn,
              color: "#fff",
              fontFamily: "var(--font-sans)",
              fontWeight: 500,
              fontSize: "0.875rem",
              cursor: "pointer",
              transition: "background var(--dur-fast)",
            }}
          >
            <Icon name="play_arrow" size={18} />
            Estudar Agora
          </button>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div>
      <p style={{ margin: 0, fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", color: "var(--text-muted)" }}>{label}</p>
      <p className="cc-num" style={{ margin: 0, fontFamily: "var(--font-sans)", fontWeight: 700, fontSize: "1.25rem", color: accent ? "var(--color-primary)" : value === 0 && label.includes("Revisar") ? "var(--text-faint)" : "var(--text-strong)" }}>{value}</p>
    </div>
  );
}
