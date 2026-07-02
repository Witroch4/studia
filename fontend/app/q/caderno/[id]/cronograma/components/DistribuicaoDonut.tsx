"use client";
import { useState } from "react";
import type { Kpis } from "../api";

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

/**
 * Distribuição do caderno em rosca: certas / erradas / restantes. O centro
 * mostra a taxa de acerto; ao passar o mouse (ou focar) num segmento, o centro
 * vira o detalhe daquele segmento. Legenda com contagens ao lado — os números
 * nunca dependem só da cor.
 */
export function DistribuicaoDonut({ kpis }: { kpis: Kpis }) {
  const [hover, setHover] = useState<number | null>(null);

  const segs = [
    { label: "Certas", valor: kpis.acertos, cor: "var(--success)" },
    { label: "Erradas", valor: kpis.erros, cor: "var(--error)" },
    { label: "Restantes", valor: kpis.restantes, cor: "var(--text-faint)", opacity: 0.35 },
    // Anuladas fecham o círculo (caderno bruto), mas estão fora do total/meta.
    ...((kpis.anuladas ?? 0) > 0
      ? [{ label: "Anuladas", valor: kpis.anuladas, cor: "var(--warning)", opacity: 0.7 }]
      : []),
  ];
  const total = Math.max(kpis.total + (kpis.anuladas ?? 0), 1);

  const S = 176, cx = S / 2, cy = S / 2, rO = 82, rI = 56;
  const rMid = (rO + rI) / 2;
  const pad = 1 / rMid; // ~2px de respiro entre segmentos, em radianos

  const visiveis = segs.filter((s) => s.valor > 0);
  let a = -Math.PI / 2;
  const arcos = segs.map((s) => {
    if (s.valor <= 0) return null;
    const span = (s.valor / total) * TAU;
    const gap = visiveis.length > 1 ? pad : 0;
    const d = arcPath(cx, cy, rO, rI, a + gap, Math.max(a + span - gap, a + gap + 0.004));
    a += span;
    return d;
  });

  const centro = hover != null && segs[hover].valor > 0
    ? { grande: segs[hover].valor.toLocaleString("pt-BR"), pequeno: segs[hover].label.toLowerCase() }
    : { grande: `${Math.round(kpis.pct_acerto * 100)}%`, pequeno: "de acerto" };

  return (
    <div className="flex flex-col sm:flex-row items-center gap-5">
      <svg
        width={S}
        height={S}
        role="img"
        aria-label={`Distribuição: ${kpis.acertos} certas, ${kpis.erros} erradas, ${kpis.restantes} restantes${(kpis.anuladas ?? 0) > 0 ? `, ${kpis.anuladas} anuladas` : ""} de ${kpis.total + (kpis.anuladas ?? 0)}.`}
        className="shrink-0"
      >
        {kpis.resolvidas === 0 && kpis.restantes === 0 && (
          <circle cx={cx} cy={cy} r={rMid} fill="none" stroke="var(--border-default)" strokeWidth={rO - rI} />
        )}
        {segs.map((s, i) =>
          arcos[i] ? (
            <path
              key={s.label}
              d={arcos[i]!}
              fill={s.cor}
              opacity={hover != null && hover !== i ? 0.4 : (s.opacity ?? 1)}
              className="transition-opacity cursor-default focus-visible:outline-2 focus-visible:outline-primary"
              tabIndex={0}
              role="img"
              aria-label={`${s.label}: ${s.valor}`}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <title>{`${s.label}: ${s.valor}`}</title>
            </path>
          ) : null
        )}
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize={26} fontWeight={600} fill="var(--text-strong)">
          {centro.grande}
        </text>
        <text x={cx} y={cy + 18} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
          {centro.pequeno}
        </text>
      </svg>

      <ul className="space-y-2 text-sm min-w-0">
        {segs.map((s, i) => (
          <li
            key={s.label}
            className="flex items-center gap-2"
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
          >
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: s.cor, opacity: s.opacity ?? 1 }} />
            <span className="text-fg-muted">{s.label}</span>
            <span className="ml-auto font-semibold text-fg tabular-nums">{s.valor.toLocaleString("pt-BR")}</span>
          </li>
        ))}
        <li className="flex items-center gap-2 pt-1 border-t border-border/50 text-xs text-fg-faint">
          <span>Resolvidas</span>
          <span className="ml-auto tabular-nums">{kpis.resolvidas.toLocaleString("pt-BR")} de {kpis.total.toLocaleString("pt-BR")}</span>
        </li>
      </ul>
    </div>
  );
}
