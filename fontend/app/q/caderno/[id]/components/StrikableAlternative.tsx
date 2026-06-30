"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

interface StrikableAlternativeProps {
  id: number;
  letra: string;
  selected: boolean;
  disabled: boolean;
  struck: boolean;
  className: string;
  selectionHotspotOnly?: boolean;
  onSelect: () => void;
  onToggleStrike: () => void;
  children: ReactNode;
}

export function StrikableAlternative({
  id,
  letra,
  selected,
  disabled,
  struck,
  className,
  selectionHotspotOnly = false,
  onSelect,
  onToggleStrike,
  children,
}: StrikableAlternativeProps) {
  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const letterClass = `flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-sm ${
    selected ? "border-primary text-primary" : "border-border-strong text-fg-muted"
  }`;
  const contentClass = `flex-1 ${struck ? "text-fg-faint line-through decoration-error decoration-2" : ""}`;

  useEffect(() => {
    return () => {
      if (clickTimer.current) clearTimeout(clickTimer.current);
    };
  }, []);

  if (selectionHotspotOnly) {
    return (
      <div
        data-alternative-id={id}
        className={className}
        title="Clique na bolinha para selecionar; use o restante da alternativa para anotar"
      >
        <button
          type="button"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!disabled) onSelect();
          }}
          disabled={disabled}
          className={`${letterClass} ${
            disabled ? "pointer-events-none" : "relative z-30 pointer-events-auto hover:bg-primary/10"
          }`}
          aria-label={`Selecionar alternativa ${letra}`}
        >
          {letra}
        </button>
        <span className={contentClass}>
          {children}
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={(event) => {
        if (disabled || event.detail > 1) return;
        if (clickTimer.current) clearTimeout(clickTimer.current);
        clickTimer.current = setTimeout(() => {
          onSelect();
          clickTimer.current = null;
        }, 180);
      }}
      onDoubleClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (clickTimer.current) {
          clearTimeout(clickTimer.current);
          clickTimer.current = null;
        }
        onToggleStrike();
      }}
      disabled={disabled}
      data-alternative-id={id}
      className={className}
      title="Dois cliques riscam ou restauram esta alternativa"
    >
      <span className={letterClass}>
        {letra}
      </span>
      <span className={contentClass}>
        {children}
      </span>
    </button>
  );
}
