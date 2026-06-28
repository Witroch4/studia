import type { CSSProperties } from "react";
import { LogoMark } from "../Logo";

/**
 * BrandLoader — loader da marca studIA para operações LENTAS / de duração
 * incerta (ex.: importar comentários sob demanda, que vão à fonte externa via
 * scraper e podem levar vários segundos). Nesses casos use isto, e NÃO um
 * spinner simples nem um texto solto — sinaliza ao usuário que a espera é
 * esperada e o app está vivo.
 *
 * Os 3 pontinhos são animados em SVG puro (SMIL `<animate>`), auto-contidos —
 * sem depender de CSS global. A logo ganha um halo que "respira" (animate-pulse).
 *
 * Para carga rápida de banco, prefira <Skeleton> (reserva o espaço do conteúdo).
 * Server-safe (sem hooks).
 */
export interface BrandLoaderProps {
  /** Texto abaixo dos pontinhos. Evite mencionar a fonte ("TC"/"tec") na UI. */
  label?: string;
  /** Tamanho da logo (px). */
  size?: number;
  className?: string;
  style?: CSSProperties;
}

export function BrandLoader({
  label = "Buscando…",
  size = 46,
  className = "",
  style,
}: BrandLoaderProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={`flex flex-col items-center justify-center gap-3 text-center ${className}`}
      style={style}
    >
      <span className="relative inline-flex">
        <span
          aria-hidden
          className="absolute inset-0 animate-pulse rounded-2xl blur-lg"
          style={{
            background:
              "radial-gradient(60% 60% at 50% 50%, color-mix(in oklab, var(--color-primary) 38%, transparent), transparent)",
          }}
        />
        <LogoMark size={size} className="relative" />
      </span>

      <svg width="48" height="14" viewBox="0 0 48 14" fill="none" aria-hidden>
        <defs>
          <linearGradient
            id="brand-loader-dots"
            x1="0"
            y1="0"
            x2="48"
            y2="0"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#22d3ee" />
            <stop offset="0.5" stopColor="#06b6d4" />
            <stop offset="1" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        {[7, 24, 41].map((cx, i) => (
          <circle key={cx} cx={cx} cy="7" r="3.5" fill="url(#brand-loader-dots)">
            <animate
              attributeName="opacity"
              values="0.25;1;0.25"
              keyTimes="0;0.5;1"
              dur="1.05s"
              begin={`${i * 0.16}s`}
              calcMode="spline"
              keySplines="0.4 0 0.2 1;0.4 0 0.2 1"
              repeatCount="indefinite"
            />
            <animate
              attributeName="r"
              values="3;5;3"
              keyTimes="0;0.5;1"
              dur="1.05s"
              begin={`${i * 0.16}s`}
              calcMode="spline"
              keySplines="0.4 0 0.2 1;0.4 0 0.2 1"
              repeatCount="indefinite"
            />
          </circle>
        ))}
      </svg>

      <p className="text-sm text-fg-faint">{label}</p>
    </div>
  );
}
