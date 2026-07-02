"use client";

import { useState } from "react";

const TAU = Math.PI * 2;

function pt(cx: number, cy: number, r: number, a: number): [number, number] {
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function arcPath(cx: number, cy: number, rO: number, rI: number, a0: number, a1: number) {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = pt(cx, cy, rO, a0);
  const [x1, y1] = pt(cx, cy, rO, a1);
  const [x2, y2] = pt(cx, cy, rI, a1);
  const [x3, y3] = pt(cx, cy, rI, a0);
  return `M${x0} ${y0} A${rO} ${rO} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${rI} ${rI} 0 ${large} 0 ${x3} ${y3} Z`;
}

export interface DonutSegmento {
  label: string;
  valor: number;
  cor: string;
  opacity?: number;
}

const nf = (n: number) => n.toLocaleString("pt-BR");

/**
 * Rosca genérica em SVG puro (tokens de tema, claro/escuro): centro mostra a
 * taxa; hover/foco num segmento troca o centro pelo detalhe. Legenda embaixo —
 * os números nunca dependem só da cor.
 */
export function DonutChart({ segs, centroGrande, centroPequeno, ariaLabel, size = 176 }: {
  segs: DonutSegmento[];
  centroGrande: string;
  centroPequeno: string;
  ariaLabel: string;
  size?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = Math.max(segs.reduce((s, x) => s + x.valor, 0), 1);

  const S = size, cx = S / 2, cy = S / 2, rO = S * 0.466, rI = S * 0.33;
  const rMid = (rO + rI) / 2;
  const pad = 1 / rMid;

  const visiveis = segs.filter((s) => s.valor > 0);
  const arcos: Array<string | null> = [];
  for (let i = 0, a = -Math.PI / 2; i < segs.length; i++) {
    const s = segs[i];
    if (s.valor <= 0) {
      arcos.push(null);
      continue;
    }
    const span = (s.valor / total) * TAU;
    const gap = visiveis.length > 1 ? pad : 0;
    arcos.push(arcPath(cx, cy, rO, rI, a + gap, Math.max(a + span - gap, a + gap + 0.004)));
    a += span;
  }

  const centro = hover != null && segs[hover].valor > 0
    ? { grande: nf(segs[hover].valor), pequeno: segs[hover].label.toLowerCase() }
    : { grande: centroGrande, pequeno: centroPequeno };

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width={S} height={S} role="img" aria-label={ariaLabel} className="shrink-0">
        {visiveis.length === 0 && (
          <circle cx={cx} cy={cy} r={rMid} fill="none" stroke="var(--border-default)" strokeWidth={rO - rI} />
        )}
        {segs.map((s, i) =>
          arcos[i] ? (
            <path
              key={s.label}
              d={arcos[i]!}
              fill={s.cor}
              opacity={hover != null && hover !== i ? 0.35 : (s.opacity ?? 1)}
              className="transition-opacity cursor-default focus-visible:outline-2 focus-visible:outline-primary"
              tabIndex={0}
              role="img"
              aria-label={`${s.label}: ${s.valor}`}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <title>{`${s.label}: ${nf(s.valor)}`}</title>
            </path>
          ) : null
        )}
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize={S * 0.153} fontWeight={700} fill="var(--text-strong)">
          {centro.grande}
        </text>
        <text x={cx} y={cy + S * 0.1} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
          {centro.pequeno}
        </text>
      </svg>
      <ul className="grid grid-cols-2 gap-x-5 gap-y-1 text-xs">
        {segs.map((s, i) => (
          <li
            key={s.label}
            className="flex items-center gap-1.5"
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
          >
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: s.cor, opacity: s.opacity ?? 1 }} />
            <span className="text-fg-muted">{s.label}</span>
            <span className="ml-auto font-semibold text-fg tabular-nums">{nf(s.valor)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
