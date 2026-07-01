"use client";

import { useEffect } from "react";

/**
 * Overlay de celebração dos combos ocultos da meta diária (25/35/45 questões
 * → COMBO X2/X3/X4). Toca o SVG animado uma única vez (~3.6s): o X é riscado
 * perna a perna como um corte de espada, o número entra com "pop" e o fogo
 * acende sobre o "X<nível>" — cada nível com chama progressivamente mais viva
 * (x4 = núcleo branco incandescente + faíscas + tremor de tela). Não bloqueia
 * cliques (pointer-events-none) e se auto-remove via onDone.
 */

type Nivel = 2 | 3 | 4;

const CFG: Record<Nivel, {
  stops: [string, string][];
  label: string;
  dispScale: number;
  dispDur: string;
  glowBlur: number;
  flameOpacity: number;
  flickDur: string;
  particles: { cx: number; cy: number; r: number; fill: string; delay: number }[];
}> = {
  2: {
    stops: [["0", "#7f1d1d"], [".5", "#dc2626"], [".85", "#f97316"], ["1", "#fbbf24"]],
    label: "#e5e5e5",
    dispScale: 12,
    dispDur: "1.6s",
    glowBlur: 3.5,
    flameOpacity: 0.55,
    flickDur: "1.1s",
    particles: [
      { cx: 175, cy: 150, r: 3, fill: "#fbbf24", delay: 0.2 },
      { cx: 225, cy: 180, r: 2.5, fill: "#f97316", delay: 0.8 },
      { cx: 320, cy: 150, r: 3, fill: "#fbbf24", delay: 1.2 },
      { cx: 350, cy: 185, r: 2, fill: "#ef4444", delay: 0.5 },
    ],
  },
  3: {
    stops: [["0", "#991b1b"], [".4", "#ef4444"], [".75", "#f97316"], ["1", "#fde047"]],
    label: "#fca5a5",
    dispScale: 20,
    dispDur: "1.1s",
    glowBlur: 5.5,
    flameOpacity: 0.8,
    flickDur: "0.7s",
    particles: [
      { cx: 170, cy: 145, r: 3.5, fill: "#fde047", delay: 0.1 },
      { cx: 200, cy: 170, r: 2.5, fill: "#f97316", delay: 0.7 },
      { cx: 232, cy: 140, r: 3, fill: "#fbbf24", delay: 1.0 },
      { cx: 255, cy: 185, r: 2, fill: "#ef4444", delay: 0.4 },
      { cx: 310, cy: 140, r: 3.5, fill: "#fde047", delay: 0.9 },
      { cx: 345, cy: 175, r: 2.5, fill: "#f97316", delay: 0.25 },
      { cx: 370, cy: 150, r: 3, fill: "#fbbf24", delay: 1.15 },
      { cx: 285, cy: 190, r: 2, fill: "#ef4444", delay: 0.55 },
    ],
  },
  4: {
    stops: [["0", "#b91c1c"], [".35", "#f97316"], [".7", "#fde047"], ["1", "#ffffff"]],
    label: "#fde047",
    dispScale: 30,
    dispDur: "0.8s",
    glowBlur: 8,
    flameOpacity: 1,
    flickDur: "0.45s",
    particles: [
      { cx: 165, cy: 140, r: 4, fill: "#ffffff", delay: 0 },
      { cx: 190, cy: 165, r: 3, fill: "#fde047", delay: 0.5 },
      { cx: 215, cy: 135, r: 3.5, fill: "#fbbf24", delay: 0.9 },
      { cx: 240, cy: 180, r: 2.5, fill: "#f97316", delay: 0.3 },
      { cx: 262, cy: 150, r: 3, fill: "#fde047", delay: 0.75 },
      { cx: 300, cy: 135, r: 4, fill: "#ffffff", delay: 0.15 },
      { cx: 330, cy: 170, r: 3, fill: "#fbbf24", delay: 0.6 },
      { cx: 360, cy: 145, r: 3.5, fill: "#fde047", delay: 1.0 },
      { cx: 385, cy: 180, r: 2.5, fill: "#f97316", delay: 0.4 },
      { cx: 205, cy: 195, r: 2, fill: "#ef4444", delay: 0.85 },
      { cx: 285, cy: 195, r: 2, fill: "#ef4444", delay: 0.2 },
      { cx: 345, cy: 195, r: 2.5, fill: "#f97316", delay: 0.95 },
      { cx: 175, cy: 120, r: 2.5, fill: "#fde047", delay: 0.65 },
      { cx: 315, cy: 115, r: 3, fill: "#ffffff", delay: 0.35 },
    ],
  },
};

const DURACAO_MS = 3700;

const LEG1 = "M156 104 L240 226";
const LEG2 = "M240 104 L156 226";

export function ComboOverlay({ nivel, onDone }: { nivel: Nivel; onDone: () => void }) {
  const cfg = CFG[nivel];
  const p = `cb${nivel}`; // prefixo p/ ids únicos de filtro/gradiente

  useEffect(() => {
    const t = setTimeout(onDone, DURACAO_MS);
    return () => clearTimeout(t);
  }, [onDone]);

  const sparks =
    nivel === 4
      ? ["l-26 -18", "l-30 6", "l-14 -30", "l24 -26", "l30 12", "l-6 32"]
      : [];

  return (
    <div className="pointer-events-none fixed inset-0 z-[9998] flex items-center justify-center">
      <svg
        viewBox="0 0 480 300"
        className="w-[min(90vw,520px)]"
        fontFamily="Arial Black, Arial, sans-serif"
        aria-label={`Combo x${nivel}`}
      >
        <defs>
          <linearGradient id={`${p}-fire`} x1="0" y1="1" x2="0" y2="0">
            {cfg.stops.map(([off, cor]) => (
              <stop key={off} offset={off} stopColor={cor} />
            ))}
          </linearGradient>
          <linearGradient id={`${p}-core`} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#fde047" />
            <stop offset="1" stopColor="#ffffff" />
          </linearGradient>
          <filter id={`${p}-flames`} x="-80%" y="-140%" width="260%" height="380%">
            <feTurbulence type="fractalNoise" baseFrequency="0.026 0.08" numOctaves="3" seed="7" result="n">
              <animate
                attributeName="baseFrequency"
                dur={cfg.dispDur}
                values="0.026 0.08;0.045 0.14;0.026 0.08"
                repeatCount="indefinite"
              />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="n" scale={cfg.dispScale} />
            <feGaussianBlur stdDeviation="3" />
          </filter>
          <filter id={`${p}-glow`} x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation={cfg.glowBlur} result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <style>{`
          .${p}-scene{animation:${p}-cycle ${DURACAO_MS}ms linear 1 both}
          @keyframes ${p}-cycle{0%,88%{opacity:1}100%{opacity:0}}
          .${p}-leg{stroke-dasharray:100;stroke-dashoffset:100;animation:${p}-leg1 ${DURACAO_MS}ms ease-out 1 both}
          @keyframes ${p}-leg1{0%,2%{stroke-dashoffset:100}8%,100%{stroke-dashoffset:0}}
          .${p}-leg.b{animation-name:${p}-leg2}
          @keyframes ${p}-leg2{0%,10%{stroke-dashoffset:100}16%,100%{stroke-dashoffset:0}}
          .${p}-flash{stroke-dasharray:100;stroke-dashoffset:100;opacity:0;animation:${p}-fl1 ${DURACAO_MS}ms ease-out 1 both}
          @keyframes ${p}-fl1{0%,2%{stroke-dashoffset:100;opacity:0}5%{opacity:1}8%{stroke-dashoffset:0}13%,100%{opacity:0;stroke-dashoffset:0}}
          .${p}-flash.b{animation-name:${p}-fl2}
          @keyframes ${p}-fl2{0%,10%{stroke-dashoffset:100;opacity:0}13%{opacity:1}16%{stroke-dashoffset:0}21%,100%{opacity:0;stroke-dashoffset:0}}
          .${p}-num{transform-box:fill-box;transform-origin:center;animation:${p}-pop ${DURACAO_MS}ms cubic-bezier(.2,1.7,.4,1) 1 both}
          @keyframes ${p}-pop{0%,16%{transform:scale(0);opacity:0}24%{transform:scale(1.25);opacity:1}30%,100%{transform:scale(1);opacity:1}}
          .${p}-flames{animation:${p}-ignite ${DURACAO_MS}ms linear 1 both}
          @keyframes ${p}-ignite{0%,18%{opacity:0}32%,100%{opacity:${cfg.flameOpacity}}}
          .${p}-flick{animation:${p}-flick ${cfg.flickDur} ease-in-out infinite}
          @keyframes ${p}-flick{0%,100%{opacity:.75}50%{opacity:1}}
          .${p}-p{animation:${p}-rise 1.3s linear infinite;opacity:0}
          @keyframes ${p}-rise{0%{transform:translateY(0);opacity:0}15%{opacity:1}100%{transform:translateY(-110px);opacity:0}}
          .${p}-shake{animation:${p}-shake .1s linear infinite}
          @keyframes ${p}-shake{0%,100%{transform:translate(0,0)}25%{transform:translate(1.4px,-1px)}50%{transform:translate(-1.2px,1.2px)}75%{transform:translate(1px,1px)}}
          .${p}-spark{animation:${p}-spark ${DURACAO_MS}ms ease-out 1 both;opacity:0}
          @keyframes ${p}-spark{0%,14%{opacity:0;transform:scale(.2)}18%{opacity:1}32%{opacity:0;transform:scale(1.6)}100%{opacity:0}}
        `}</style>
        <g className={`${p}-scene`}>
          <g className={nivel === 4 ? `${p}-shake` : undefined}>
            <text
              x="240"
              y="66"
              textAnchor="middle"
              fontSize="34"
              letterSpacing="14"
              fill={nivel === 4 ? `url(#${p}-fire)` : cfg.label}
              filter={nivel === 4 ? `url(#${p}-glow)` : undefined}
            >
              COMBO
            </text>
            {/* chamas atrás do X + número */}
            <g className={`${p}-flames`} filter={`url(#${p}-flames)`}>
              <g className={`${p}-flick`}>
                <path d={LEG1} stroke={`url(#${p}-fire)`} strokeWidth={22 + nivel * 3} strokeLinecap="round" fill="none" />
                <path d={LEG2} stroke={`url(#${p}-fire)`} strokeWidth={22 + nivel * 3} strokeLinecap="round" fill="none" />
                <text x="296" y="223" fontSize="132" fontStyle="italic" fontWeight="900" fill={`url(#${p}-fire)`}>
                  {nivel}
                </text>
              </g>
            </g>
            {/* núcleo branco-amarelo incandescente (só x4) */}
            {nivel === 4 && (
              <g className={`${p}-flames`} filter={`url(#${p}-flames)`} opacity=".85">
                <path d={LEG1} stroke={`url(#${p}-core)`} strokeWidth="16" strokeLinecap="round" fill="none" />
                <path d={LEG2} stroke={`url(#${p}-core)`} strokeWidth="16" strokeLinecap="round" fill="none" />
              </g>
            )}
            {/* partículas subindo */}
            <g className={`${p}-flames`}>
              {cfg.particles.map((pt, i) => (
                <circle
                  key={i}
                  className={`${p}-p`}
                  cx={pt.cx}
                  cy={pt.cy}
                  r={pt.r}
                  fill={pt.fill}
                  style={{ animationDelay: `${pt.delay}s` }}
                />
              ))}
            </g>
            {/* faíscas de impacto (só x4) */}
            {sparks.length > 0 && (
              <g stroke="#ffffff" strokeWidth="3" strokeLinecap="round">
                {sparks.map((d, i) => (
                  <path
                    key={i}
                    className={`${p}-spark`}
                    d={`M198 165 ${d}`}
                    style={{ transformOrigin: "198px 165px", animationDelay: `${i * 0.03}s` }}
                  />
                ))}
              </g>
            )}
            {/* X nítido: corte de espada, uma perna depois a outra */}
            <g filter={`url(#${p}-glow)`}>
              <path className={`${p}-leg`} pathLength={100} d={LEG1} stroke={`url(#${p}-fire)`} strokeWidth="20" strokeLinecap="round" fill="none" />
              <path className={`${p}-leg b`} pathLength={100} d={LEG2} stroke={`url(#${p}-fire)`} strokeWidth="20" strokeLinecap="round" fill="none" />
              <text className={`${p}-num`} x="296" y="223" fontSize="132" fontStyle="italic" fontWeight="900" fill={`url(#${p}-fire)`}>
                {nivel}
              </text>
            </g>
            {/* brilho do corte */}
            <path className={`${p}-flash`} pathLength={100} d={LEG1} stroke="#ffffff" strokeWidth="6" strokeLinecap="round" fill="none" />
            <path className={`${p}-flash b`} pathLength={100} d={LEG2} stroke="#ffffff" strokeWidth="6" strokeLinecap="round" fill="none" />
          </g>
        </g>
      </svg>
    </div>
  );
}
