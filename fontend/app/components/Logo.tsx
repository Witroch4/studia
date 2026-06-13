import type { CSSProperties } from "react";

/**
 * Marca studIA — capelo (mortarboard) em badge com gradiente ciano→violeta.
 * `LogoMark` é só o ícone; `Logo` adiciona o wordmark "studIA".
 * Componentes server-safe (sem hooks) — usáveis em qualquer lugar.
 */

export function LogoMark({
  size = 36,
  className = "",
  style,
  title = "studIA",
}: {
  size?: number;
  className?: string;
  style?: CSSProperties;
  title?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={title}
      className={className}
      style={style}
    >
      <defs>
        <linearGradient id="studia-grad" x1="6" y1="4" x2="42" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor="#22d3ee" />
          <stop offset="0.55" stopColor="#06b6d4" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="44" height="44" rx="12" fill="url(#studia-grad)" />
      <rect x="2.5" y="2.5" width="43" height="43" rx="11.5" fill="none" stroke="#ffffff" strokeOpacity="0.18" />
      {/* capelo (rombo) */}
      <path d="M24 13 41 20 24 27 7 20Z" fill="#ffffff" />
      {/* faixa que assenta na cabeça */}
      <path
        d="M17 23.4 24 26.3 31 23.4V28.6C31 30.9 27.9 32.6 24 32.6 20.1 32.6 17 30.9 17 28.6Z"
        fill="#ffffff"
        fillOpacity="0.92"
      />
      {/* borla + missanga */}
      <path d="M40.4 20V30.5" stroke="#ffffff" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="40.4" cy="32.4" r="2.1" fill="#ffffff" />
    </svg>
  );
}

export default function Logo({
  size = 32,
  withWord = true,
  className = "",
  wordClassName = "text-2xl",
}: {
  size?: number;
  withWord?: boolean;
  className?: string;
  wordClassName?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={size} />
      {withWord && (
        <span className={`font-bold tracking-tight leading-none text-fg-strong ${wordClassName}`}>
          stud
          <span className="bg-gradient-to-br from-primary to-secondary bg-clip-text text-transparent">IA</span>
        </span>
      )}
    </span>
  );
}
