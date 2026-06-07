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
  onSelect,
  onToggleStrike,
  children,
}: StrikableAlternativeProps) {
  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (clickTimer.current) clearTimeout(clickTimer.current);
    };
  }, []);

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
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-sm ${
          selected ? "border-cyan-400 text-cyan-300" : "border-gray-600 text-gray-400"
        }`}
      >
        {letra}
      </span>
      <span className={`flex-1 ${struck ? "text-gray-500 line-through decoration-red-500 decoration-2" : ""}`}>
        {children}
      </span>
    </button>
  );
}
